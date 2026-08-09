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

## Maintenir le catalogue

Depuis PowerShell :

```powershell
.\nzo-repo.cmd check
.\nzo-repo.cmd smoke
.\nzo-repo.cmd add "..\NZO - NOUVEAU PLUGIN\nzo_nouveau_plugin"
.\nzo-repo.cmd publish
```

`check` et `publish` exigent un Blender récent. Définir `NZO_BLENDER_EXE` pour imposer
un exécutable précis. `publish` exige également `gh`, une session GitHub authentifiée et
le droit d'écrire dans `Nozomagarion/NZO-BLENDER-EXTENSIONS`.

Une combinaison ID/version publiée est immuable. Toute modification impose une nouvelle
version dans `blender_manifest.toml`.

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
