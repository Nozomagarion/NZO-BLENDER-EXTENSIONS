from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any


if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(errors="replace")


ROOT = Path(__file__).resolve().parents[1]
WORKSPACE_ROOT = ROOT.parent
CATALOG_PATH = ROOT / "catalog.toml"
POLICY_TEMPLATE_PATH = ROOT / "templates" / "PLUGIN_AGENTS.md"
BUILD_ROOT = ROOT / ".build"
PACKAGE_DIR = BUILD_ROOT / "packages"
STAGING_DIR = BUILD_ROOT / "staging"
DOCS_DIR = ROOT / "docs"
SEMVER = re.compile(r"^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$")
POLICY_START = "<!-- NZO_RELEASE_POLICY_START -->"
POLICY_END = "<!-- NZO_RELEASE_POLICY_END -->"


class RepoError(RuntimeError):
    pass


@dataclass(frozen=True)
class Package:
    package_id: str
    version: str
    name: str
    source: Path
    archive: Path
    manifest: dict[str, Any]

    @property
    def tag(self) -> str:
        return f"{self.package_id}-v{self.version}"


def run(
    command: list[str],
    *,
    cwd: Path | None = None,
    capture: bool = True,
    env: dict[str, str] | None = None,
) -> str:
    printable = subprocess.list2cmdline(command)
    print(f"> {printable}")
    result = subprocess.run(
        command,
        cwd=cwd,
        text=True,
        encoding="utf-8",
        errors="replace",
        capture_output=capture,
        env=env,
    )
    output = ((result.stdout or "") + (result.stderr or "")).strip()
    if result.returncode:
        raise RepoError(f"Commande échouée ({result.returncode}) : {printable}\n{output}")
    if output:
        print(output)
    return output


def load_catalog() -> dict[str, Any]:
    with CATALOG_PATH.open("rb") as handle:
        data = tomllib.load(handle)
    if data.get("schema_version") != "1.0.0":
        raise RepoError("Version de catalog.toml non prise en charge")
    return data


def parse_version(value: str) -> tuple[int, int, int]:
    match = re.match(r"^(\d+)\.(\d+)\.(\d+)", value)
    if not match:
        raise RepoError(f"Version invalide : {value}")
    return tuple(int(part) for part in match.groups())


def read_utf8(path: Path) -> tuple[str, bool]:
    data = path.read_bytes()
    has_bom = data.startswith(b"\xef\xbb\xbf")
    return data.decode("utf-8-sig" if has_bom else "utf-8"), has_bom


def write_utf8(path: Path, text: str, *, bom: bool = False) -> None:
    data = text.encode("utf-8")
    path.write_bytes((b"\xef\xbb\xbf" if bom else b"") + data)


def catalog_entry(package_id: str) -> dict[str, Any]:
    matches = [entry for entry in load_catalog().get("extensions", []) if entry["id"] == package_id]
    if not matches:
        raise RepoError(f"Extension inconnue : {package_id}")
    if len(matches) > 1:
        raise RepoError(f"ID dupliqué dans le catalogue : {package_id}")
    return matches[0]


def bumped_version(current: str, level: str) -> str:
    major, minor, patch = parse_version(current)
    if level == "patch":
        patch += 1
    elif level == "minor":
        minor, patch = minor + 1, 0
    elif level == "major":
        major, minor, patch = major + 1, 0, 0
    else:
        raise RepoError(f"Niveau de version inconnu : {level}")
    return f"{major}.{minor}.{patch}"


def replace_manifest_version(text: str, current: str, updated: str) -> str:
    pattern = re.compile(r'(?m)^(\s*version\s*=\s*)["\']([^"\']+)["\'](\s*(?:#.*)?)$')
    matching = [match for match in pattern.finditer(text) if match.group(2) == current]
    if len(matching) != 1:
        raise RepoError("La ligne de version du manifest est absente ou ambiguë")
    target = matching[0]
    replacement = f'{target.group(1)}"{updated}"{target.group(3)}'
    return text[:target.start()] + replacement + text[target.end():]


def replace_bl_info_version(text: str, updated: str) -> tuple[str, bool]:
    block_match = re.search(r"(?ms)^bl_info\s*=\s*\{.*?^\}", text)
    if block_match is None:
        return text, False
    block = block_match.group(0)
    version_pattern = re.compile(
        r'(?m)^(\s*["\']version["\']\s*:\s*)\(\s*\d+\s*,\s*\d+\s*,\s*\d+\s*\)(\s*,?\s*)$'
    )
    match = version_pattern.search(block)
    if match is None:
        return text, False
    version_tuple = ", ".join(updated.split("."))
    replacement = f"{match.group(1)}({version_tuple}){match.group(2)}"
    changed_block = block[:match.start()] + replacement + block[match.end():]
    return text[:block_match.start()] + changed_block + text[block_match.end():], True


def bump_extension(package_id: str, level: str, *, dry_run: bool = False) -> None:
    entry = catalog_entry(package_id)
    source = (ROOT / entry["source"]).resolve()
    manifest_path = source / "blender_manifest.toml"
    manifest = read_manifest(source)
    current = str(manifest.get("version", ""))
    if not SEMVER.fullmatch(current):
        raise RepoError(f"Version non sémantique pour {package_id}: {current}")
    updated = bumped_version(current, level)
    manifest_text, manifest_bom = read_utf8(manifest_path)
    updated_manifest = replace_manifest_version(manifest_text, current, updated)

    entrypoint = source / entry.get("entrypoint", "__init__.py")
    updated_entrypoint: str | None = None
    synchronized = False
    entrypoint_bom = False
    if entrypoint.is_file():
        entrypoint_text, entrypoint_bom = read_utf8(entrypoint)
        updated_entrypoint, synchronized = replace_bl_info_version(entrypoint_text, updated)

    print(f"{package_id}: {current} -> {updated} ({level})")
    print(f"Archive attendue : {package_id}-{updated}.zip")
    if synchronized:
        print(f"bl_info synchronisé : {entrypoint}")
    if dry_run:
        print("Simulation uniquement : aucun fichier modifié.")
        return

    write_utf8(manifest_path, updated_manifest, bom=manifest_bom)
    if synchronized and updated_entrypoint is not None:
        write_utf8(entrypoint, updated_entrypoint, bom=entrypoint_bom)
    print("Version mise à jour. Lancez ensuite : nzo-repo.cmd check")


def policy_block(template: str, extension_ids: list[str]) -> str:
    start = template.find(POLICY_START)
    end = template.find(POLICY_END)
    if start < 0 or end < start:
        raise RepoError(f"Marqueurs de politique absents : {POLICY_TEMPLATE_PATH}")
    end += len(POLICY_END)
    return template[start:end].replace("{{EXTENSION_IDS}}", ", ".join(extension_ids))


def project_root(source: Path) -> Path:
    try:
        relative = source.relative_to(WORKSPACE_ROOT)
    except ValueError:
        return source
    if not relative.parts:
        raise RepoError(f"Source de plugin invalide : {source}")
    return WORKSPACE_ROOT / relative.parts[0]


def sync_policy(*, dry_run: bool = False) -> None:
    template, _ = read_utf8(POLICY_TEMPLATE_PATH)
    projects: dict[Path, list[str]] = {}
    for entry in load_catalog().get("extensions", []):
        source = (ROOT / entry["source"]).resolve()
        projects.setdefault(project_root(source), []).append(str(entry["id"]))

    changed = 0
    for project, extension_ids in sorted(projects.items(), key=lambda item: str(item[0]).lower()):
        agent_path = project / "AGENTS.md"
        block = policy_block(template, sorted(extension_ids))
        existing: str | None = None
        existing_bom = False
        if agent_path.is_file():
            existing, existing_bom = read_utf8(agent_path)
            start = existing.find(POLICY_START)
            end = existing.find(POLICY_END)
            if start >= 0 and end >= start:
                end += len(POLICY_END)
                updated = existing[:start] + block + existing[end:]
            else:
                updated = existing.rstrip() + "\n\n" + block + "\n"
        else:
            updated = template.replace("{{EXTENSION_IDS}}", ", ".join(sorted(extension_ids)))
        if existing == updated:
            continue
        changed += 1
        action = "Mettrait à jour" if dry_run else "Mis à jour"
        print(f"{action} : {agent_path}")
        if not dry_run:
            write_utf8(agent_path, updated, bom=existing_bom)
    suffix = " à modifier" if dry_run else " synchronisé(s)"
    print(f"{changed} fichier(s) AGENTS.md{suffix} sur {len(projects)} projet(s).")


def find_blender() -> Path:
    explicit = os.environ.get("NZO_BLENDER_EXE")
    candidates: list[Path] = []
    if explicit:
        candidate = Path(explicit)
        try:
            output = subprocess.run(
                [str(candidate), "--version"],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise RepoError(f"NZO_BLENDER_EXE est inutilisable : {candidate}") from exc
        if output.returncode or not re.search(r"Blender\s+\d+\.\d+\.\d+", output.stdout):
            raise RepoError(f"NZO_BLENDER_EXE est inutilisable : {candidate}")
        return candidate.resolve()
    if os.name == "nt":
        program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
        candidates.extend((program_files / "Blender Foundation").glob("Blender */blender.exe"))
    command = shutil.which("blender")
    if command:
        candidates.append(Path(command))

    usable: list[tuple[tuple[int, int, int], Path]] = []
    for candidate in candidates:
        if not candidate.is_file():
            continue
        try:
            output = subprocess.run(
                [str(candidate), "--version"],
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=20,
            )
        except (OSError, subprocess.SubprocessError):
            continue
        match = re.search(r"Blender\s+(\d+)\.(\d+)\.(\d+)", output.stdout)
        if output.returncode == 0 and match:
            usable.append((tuple(int(v) for v in match.groups()), candidate.resolve()))
    if not usable:
        raise RepoError("Aucun exécutable Blender utilisable n'a été trouvé")
    return max(usable, key=lambda item: item[0])[1]


def read_manifest(source: Path) -> dict[str, Any]:
    manifest_path = source / "blender_manifest.toml"
    if not manifest_path.is_file():
        raise RepoError(f"Manifest manquant : {manifest_path}")
    with manifest_path.open("rb") as handle:
        return tomllib.load(handle)


def validate_contract(entry: dict[str, Any], source: Path, manifest: dict[str, Any]) -> None:
    expected_id = entry["id"]
    if manifest.get("id") != expected_id:
        raise RepoError(f"ID incohérent pour {source}: {manifest.get('id')} != {expected_id}")
    version = str(manifest.get("version", ""))
    if not SEMVER.fullmatch(version):
        raise RepoError(f"Version non sémantique pour {expected_id}: {version}")
    minimum = str(manifest.get("blender_version_min", ""))
    if parse_version(minimum) < (4, 2, 0):
        raise RepoError(f"{expected_id} doit cibler Blender 4.2.0 ou plus")
    licenses = manifest.get("license")
    if not isinstance(licenses, list) or not licenses:
        raise RepoError(f"Licence absente pour {expected_id}")
    if not (source / "LICENSE").is_file():
        raise RepoError(f"Fichier LICENSE absent pour {expected_id}")
    if entry.get("mode", "directory") == "directory" and not (source / "__init__.py").is_file():
        raise RepoError(f"__init__.py absent pour {expected_id}")


def stage_source(entry: dict[str, Any], source: Path) -> Path:
    if entry.get("mode", "directory") == "directory":
        return source
    if entry["mode"] != "single_file":
        raise RepoError(f"Mode inconnu pour {entry['id']}: {entry['mode']}")

    target = STAGING_DIR / entry["id"]
    target.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / entry["entrypoint"], target / "__init__.py")
    shutil.copy2(source / "blender_manifest.toml", target / "blender_manifest.toml")
    shutil.copy2(source / "LICENSE", target / "LICENSE")
    for relative in entry.get("extras", []):
        extra = source / relative
        if not extra.is_file():
            raise RepoError(f"Fichier supplémentaire absent : {extra}")
        shutil.copy2(extra, target / extra.name)
    return target


def compile_archive(archive: Path) -> None:
    with zipfile.ZipFile(archive) as bundle:
        names = set(bundle.namelist())
        suffixes = {Path(name).name for name in names}
        if "blender_manifest.toml" not in suffixes or "__init__.py" not in suffixes:
            raise RepoError(f"Archive incomplète : {archive.name}")
        for name in names:
            if not name.endswith(".py"):
                continue
            data = bundle.read(name)
            try:
                source = data.decode("utf-8-sig")
                compile(source, f"{archive.name}/{name}", "exec")
            except (UnicodeDecodeError, SyntaxError) as exc:
                raise RepoError(f"Python invalide dans {archive.name}/{name}: {exc}") from exc


def build_all() -> tuple[dict[str, Any], list[Package], Path]:
    catalog = load_catalog()
    blender = find_blender()
    print(f"Blender de construction : {blender}")

    if BUILD_ROOT.exists():
        shutil.rmtree(BUILD_ROOT)
    PACKAGE_DIR.mkdir(parents=True)
    STAGING_DIR.mkdir(parents=True)

    packages: list[Package] = []
    seen: set[str] = set()
    for entry in catalog.get("extensions", []):
        package_id = entry["id"]
        if package_id in seen:
            raise RepoError(f"ID dupliqué dans le catalogue : {package_id}")
        seen.add(package_id)

        source = (ROOT / entry["source"]).resolve()
        manifest = read_manifest(source)
        validate_contract(entry, source, manifest)
        build_source = stage_source(entry, source)

        run([str(blender), "--factory-startup", "--command", "extension", "validate", str(build_source)])
        before = set(PACKAGE_DIR.glob("*.zip"))
        run([
            str(blender),
            "--factory-startup",
            "--command",
            "extension",
            "build",
            "--source-dir",
            str(build_source),
            "--output-dir",
            str(PACKAGE_DIR),
        ])
        created = list(set(PACKAGE_DIR.glob("*.zip")) - before)
        if len(created) != 1:
            raise RepoError(f"Construction ambiguë pour {package_id}: {created}")
        archive = created[0]
        run([str(blender), "--factory-startup", "--command", "extension", "validate", str(archive)])
        compile_archive(archive)
        packages.append(Package(
            package_id=package_id,
            version=str(manifest["version"]),
            name=str(manifest["name"]),
            source=source,
            archive=archive,
            manifest=manifest,
        ))

    print(f"\n{len(packages)} extensions construites et validées.")
    return catalog, packages, blender


def load_built_packages() -> tuple[dict[str, Any], list[Package], Path]:
    catalog = load_catalog()
    blender = find_blender()
    packages: list[Package] = []
    for entry in catalog.get("extensions", []):
        source = (ROOT / entry["source"]).resolve()
        manifest = read_manifest(source)
        archive = PACKAGE_DIR / f"{manifest['id']}-{manifest['version']}.zip"
        if not archive.is_file():
            raise RepoError("Artefacts absents : exécutez d'abord 'nzo-repo.cmd check'")
        packages.append(Package(
            package_id=str(manifest["id"]),
            version=str(manifest["version"]),
            name=str(manifest["name"]),
            source=source,
            archive=archive,
            manifest=manifest,
        ))
    return catalog, packages, blender


def smoke_all() -> None:
    _, packages, blender = load_built_packages()
    version_output = run([str(blender), "--version"])
    version_match = re.search(r"Blender\s+(\d+\.\d+\.\d+)", version_output)
    if version_match is None:
        raise RepoError(f"Version Blender illisible : {blender}")
    tested_version = parse_version(version_match.group(1))
    packages = [
        package for package in packages
        if parse_version(str(package.manifest["blender_version_min"])) <= tested_version
        and (
            "blender_version_max" not in package.manifest
            or tested_version < parse_version(str(package.manifest["blender_version_max"]))
        )
    ]
    smoke_root = BUILD_ROOT / "smoke" / version_match.group(1)
    if smoke_root.exists():
        shutil.rmtree(smoke_root)
    smoke_root.mkdir(parents=True)

    for package in packages:
        profile = smoke_root / package.package_id
        config = profile / "config"
        extensions = profile / "extensions"
        repository = profile / "repo"
        for directory in (config, extensions, repository):
            directory.mkdir(parents=True)
        environment = os.environ.copy()
        environment["BLENDER_USER_CONFIG"] = str(config)
        environment["BLENDER_USER_EXTENSIONS"] = str(extensions)
        environment["BLENDER_USER_RESOURCES"] = str(profile / "resources")

        run([
            str(blender), "--factory-startup", "--command", "extension", "repo-add",
            "--name", "NZO Smoke", "--directory", str(repository), "smoke",
        ], env=environment)
        run([
            str(blender), "--command", "extension", "install-file",
            "-r", "smoke", "-e", str(package.archive),
        ], env=environment)
        module_name = f"bl_ext.smoke.{package.package_id}"
        expression = (
            "import bpy; "
            f"name={module_name!r}; "
            "assert name in bpy.context.preferences.addons, "
            "f'extension non active: {name}'; "
            "print(f'SMOKE_OK={name}')"
        )
        output = run([
            str(blender), "--background", "--python-expr", expression,
        ], env=environment)
        if f"SMOKE_OK={module_name}" not in output:
            raise RepoError(f"Confirmation d'activation absente pour {package.package_id}")
    print(f"\n{len(packages)} extensions installées et activées dans des profils isolés.")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def gh_json(arguments: list[str]) -> Any:
    output = run(["gh", *arguments])
    return json.loads(output) if output else None


def ensure_release(repo: str, package: Package, previous_entries: list[dict[str, Any]]) -> str:
    release: dict[str, Any] | None
    try:
        release = gh_json(["release", "view", package.tag, "-R", repo, "--json", "assets,url"])
    except RepoError:
        release = None

    if release is None:
        run([
            "gh", "release", "create", package.tag,
            "-R", repo,
            "--title", f"{package.name} {package.version}",
            "--notes", f"Blender Extension package for {package.name} {package.version}.",
            "--latest=false",
        ])
        assets: list[dict[str, Any]] = []
    else:
        assets = release.get("assets", [])

    asset = next((item for item in assets if item.get("name") == package.archive.name), None)
    local_hash = sha256(package.archive)
    if asset is not None:
        previous = next(
            (
                item for item in previous_entries
                if item.get("id") == package.package_id
                and item.get("version") == package.version
                and str(item.get("archive_url", "")).endswith("/" + package.archive.name)
            ),
            None,
        )
        previous_hash = str((previous or {}).get("archive_hash", "")).removeprefix("sha256:")
        if previous_hash != local_hash:
            raise RepoError(
                f"Release immuable en conflit pour {package.package_id} {package.version}; "
                "incrémentez la version du manifest"
            )
    else:
        run(["gh", "release", "upload", package.tag, str(package.archive), "-R", repo])

    filename = urllib.parse.quote(package.archive.name)
    return f"https://github.com/{repo}/releases/download/{package.tag}/{filename}"


def package_key(item: dict[str, Any]) -> tuple[str, str, tuple[str, ...]]:
    platforms = tuple(sorted(item.get("platforms", [])))
    return str(item.get("id", "")), str(item.get("version", "")), platforms


def generate_html(index: dict[str, Any], title: str) -> str:
    rows = []
    for item in sorted(index.get("data", []), key=lambda value: (value.get("name", ""), value.get("version", ""))):
        name = html.escape(str(item.get("name", item.get("id", ""))))
        version = html.escape(str(item.get("version", "")))
        minimum = html.escape(str(item.get("blender_version_min", "")))
        tagline = html.escape(str(item.get("tagline", "")))
        url = html.escape(str(item.get("archive_url", "")), quote=True)
        rows.append(
            f'<article><h2>{name} <small>{version}</small></h2>'
            f'<p>{tagline}</p><p>Blender {minimum}+ · <a href="{url}">Télécharger le ZIP</a></p></article>'
        )
    body = "\n".join(rows)
    return f"""<!doctype html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{html.escape(title)}</title><style>
body{{font:16px/1.5 system-ui,sans-serif;max-width:900px;margin:40px auto;padding:0 20px;background:#111;color:#eee}}
a{{color:#7cc7ff}} article{{border:1px solid #333;border-radius:12px;padding:12px 18px;margin:14px 0;background:#181818}}
h1{{margin-bottom:4px}} h2{{margin:0}} small{{color:#aaa;font-weight:400}} code{{background:#222;padding:2px 5px}}
</style></head><body><h1>{html.escape(title)}</h1>
<p>Ajoutez <code>index.json</code> comme dépôt distant dans Blender 4.2 ou plus récent.</p>{body}</body></html>"""


def publish(*, reuse_build: bool = False) -> None:
    if reuse_build:
        catalog, packages, blender = load_built_packages()
    else:
        catalog, packages, blender = build_all()
    repository = catalog["repository"]
    repo = repository["github"]
    run(["gh", "auth", "status"])
    run(["gh", "repo", "view", repo, "--json", "nameWithOwner"])

    previous_index_path = DOCS_DIR / "index.json"
    if previous_index_path.is_file():
        previous_index = json.loads(previous_index_path.read_text(encoding="utf-8"))
    else:
        previous_index = {"version": "v1", "blocklist": [], "data": []}
    previous_entries = list(previous_index.get("data", []))

    server_dir = BUILD_ROOT / "server"
    server_dir.mkdir(parents=True)
    for package in packages:
        shutil.copy2(package.archive, server_dir / package.archive.name)
    run([
        str(blender), "--factory-startup", "--command", "extension", "server-generate",
        "--repo-dir", str(server_dir), "--html",
    ])
    generated = json.loads((server_dir / "index.json").read_text(encoding="utf-8"))

    package_by_filename = {item.archive.name: item for item in packages}
    new_entries = []
    for item in generated.get("data", []):
        filename = Path(str(item["archive_url"])).name
        package = package_by_filename.get(filename)
        if package is None:
            raise RepoError(f"Archive inconnue dans l'index généré : {filename}")
        item["archive_url"] = ensure_release(repo, package, previous_entries)
        new_entries.append(item)

    merged = {package_key(item): item for item in previous_entries}
    for item in new_entries:
        merged[package_key(item)] = item
    final_index = {
        "version": generated.get("version", "v1"),
        "blocklist": generated.get("blocklist", []),
        "data": list(merged.values()),
    }

    DOCS_DIR.mkdir(parents=True, exist_ok=True)
    (DOCS_DIR / ".nojekyll").write_text("", encoding="utf-8")
    (DOCS_DIR / "index.json").write_text(
        json.dumps(final_index, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8",
    )
    (DOCS_DIR / "index.html").write_text(
        generate_html(final_index, repository["display_name"]),
        encoding="utf-8",
    )

    run(["git", "add", "docs"], cwd=ROOT)
    status = run(["git", "status", "--short", "docs"], cwd=ROOT)
    if status:
        run(["git", "commit", "-m", "Publish extension catalog"], cwd=ROOT)
        run(["git", "push", "origin", "HEAD"], cwd=ROOT)
    else:
        print("Catalogue distant déjà à jour.")


def add_extension(path_value: str) -> None:
    source = Path(path_value).expanduser().resolve()
    manifest = read_manifest(source)
    package_id = str(manifest.get("id", ""))
    if not package_id:
        raise RepoError("Le manifest ne contient pas d'ID")
    catalog = load_catalog()
    if any(entry["id"] == package_id for entry in catalog.get("extensions", [])):
        raise RepoError(f"{package_id} est déjà enregistré")
    relative = os.path.relpath(source, ROOT).replace("\\", "/")
    with CATALOG_PATH.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(f'\n[[extensions]]\nid = {json.dumps(package_id)}\nsource = {json.dumps(relative)}\n')
    print(f"Extension ajoutée : {package_id} -> {relative}")
    sync_policy()


def main() -> int:
    parser = argparse.ArgumentParser(description="Build and publish the NZO Blender Extensions repository")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("check", help="Validate and build every registered extension")
    subparsers.add_parser("smoke", help="Install and enable every built extension in an isolated profile")
    sync_parser = subparsers.add_parser("sync-policy", help="Install the release policy in every plugin project")
    sync_parser.add_argument("--dry-run", action="store_true", help="Show changes without writing files")
    bump_parser = subparsers.add_parser("bump", help="Increment an extension version and synchronize legacy metadata")
    bump_parser.add_argument("id")
    bump_parser.add_argument("level", choices=("patch", "minor", "major"))
    bump_parser.add_argument("--dry-run", action="store_true", help="Show the new version without writing files")
    add_parser = subparsers.add_parser("add", help="Register a new extension source directory")
    add_parser.add_argument("path")
    publish_parser = subparsers.add_parser("publish", help="Build, upload immutable releases and publish the index")
    publish_parser.add_argument(
        "--reuse-build",
        action="store_true",
        help="Reuse packages from the last successful check when retrying publication",
    )
    args = parser.parse_args()

    try:
        if args.command == "check":
            build_all()
        elif args.command == "smoke":
            smoke_all()
        elif args.command == "sync-policy":
            sync_policy(dry_run=args.dry_run)
        elif args.command == "bump":
            bump_extension(args.id, args.level, dry_run=args.dry_run)
        elif args.command == "add":
            add_extension(args.path)
        elif args.command == "publish":
            publish(reuse_build=args.reuse_build)
    except RepoError as exc:
        print(f"ERREUR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
