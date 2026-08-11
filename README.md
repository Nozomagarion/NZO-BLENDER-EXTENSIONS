# NZO Blender Extensions

Catalogue public des extensions Blender de NZO. Les sources restent dans leurs projets
respectifs ; ce dépôt valide les manifests, construit les ZIP et publie l'index consommé
par Blender.

## Utiliser le catalogue dans Blender

Dans Blender 4.2 ou plus récent :

1. Ouvrir **Edit > Preferences > Get Extensions**.
2. Ouvrir le menu **Repositories** puis **Add Remote Repository**.
3. Coller cette URL :

   `https://nozomagarion.github.io/NZO-BLENDER-EXTENSIONS/index.json`

Sous Windows, double-cliquer sur `connect-nzo-repo.cmd` réalise cette opération pour toutes les versions
Blender 4.2+ détectées. Il n'installe et n'active aucune extension automatiquement.
Le script force l'accès en ligne uniquement pendant la connexion et la synchronisation.

## Maintenir le catalogue

Depuis PowerShell :

```powershell
.\nzo-repo.cmd bump nzo_bpm_sync patch
.\nzo-repo.cmd normalize-names --dry-run
.\nzo-repo.cmd check
.\nzo-repo.cmd smoke
.\nzo-repo.cmd add "..\NZO - NOUVEAU PLUGIN\nzo_nouveau_plugin"
.\nzo-repo.cmd publish
```

La commande `bump` applique le versionnement sémantique depuis la version actuelle :

- `patch` pour un correctif (`1.0.0` → `1.0.1`) ;
- `minor` pour une fonctionnalité rétrocompatible (`1.0.0` → `1.1.0`) ;
- `major` pour un changement incompatible (`1.0.0` → `2.0.0`).

Elle modifie `blender_manifest.toml`, synchronise l'ancien `bl_info["version"]` s'il
existe et annonce le nom du prochain ZIP. Le nom public de l'extension reste stable et
ne contient pas la version. Utiliser `--dry-run` pour prévisualiser sans écrire.

`sync-policy` installe ou actualise dans chaque projet un bloc `AGENTS.md` qui impose ces
règles aux agents de code. La commande `add` l'exécute automatiquement pour les nouveaux
plugins enregistrés.

Tous les noms publics respectent la forme `NZO - NOM DU PLUGIN`, avec la partie après le
tiret entièrement en majuscules. `normalize-names` corrige le manifest et l'ancien
`bl_info`, puis applique automatiquement une version `patch` à chaque extension modifiée.
`check` et `add` refusent ensuite tout nom qui ne respecte pas cette convention.

`check` et `publish` exigent un Blender récent. Définir `NZO_BLENDER_EXE` pour imposer
un exécutable précis. `publish` exige également `gh`, une session GitHub authentifiée et
le droit d'écrire dans `Nozomagarion/NZO-BLENDER-EXTENSIONS`.

Une combinaison ID/version publiée est immuable. Toute modification du paquet distribué
impose une nouvelle version dans `blender_manifest.toml`. La publication externe reste
volontaire : le changement de version ne lance jamais `publish` tout seul.

Après un échec réseau survenu après la validation, `nzo-repo.cmd publish --reuse-build`
reprend la publication avec les derniers ZIP construits par `check` ou `publish`.

## Contrat d'une extension

- `blender_manifest.toml` et `__init__.py` à la racine du paquet ;
- ID unique et version sémantique ;
- Blender 4.2.0 minimum pour utiliser ce canal ;
- licence SPDX et fichier `LICENSE` correspondant ;
- permissions, plateformes et wheels déclarées dans le manifest ;
- inscription explicite dans `catalog.toml`.

Les dossiers de test, caches, anciens ZIP et projets sans extension ne sont pas découverts
automatiquement et ne peuvent donc pas être publiés par accident.
