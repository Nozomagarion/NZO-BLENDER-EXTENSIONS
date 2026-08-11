# Instructions du projet

<!-- NZO_RELEASE_POLICY_START -->
## Publication NZO obligatoire

Cette politique s'applique à tout agent qui modifie le code distribué de ce projet.

- Extensions enregistrées : `{{EXTENSION_IDS}}`.
- `blender_manifest.toml` est la source de vérité pour l'identifiant, le nom public et la version.
- Toute modification du paquet distribué doit inclure, dans le même travail, une version strictement supérieure :
  - correctif rétrocompatible : `patch` (`1.0.0` → `1.0.1`) ;
  - fonctionnalité rétrocompatible : `minor` (`1.0.0` → `1.1.0`) ;
  - changement incompatible : `major` (`1.0.0` → `2.0.0`).
- Ne jamais diminuer, réutiliser ou réinitialiser une version déjà publiée. Pour une version `0.x`, un `major` marque le passage à `1.0.0`.
- Une modification limitée à la documentation, aux tests ou aux fichiers non empaquetés ne demande pas de nouvelle version.
- Le champ `name` respecte obligatoirement `NZO - NOM DU PLUGIN` : préfixe `NZO`, espaces autour du tiret, puis nom entièrement en majuscules et sans numéro de version.
- Le ZIP, le tag et le titre de Release sont générés automatiquement à partir de l'ID, du nom et de la version du manifest.
- Utiliser la commande centrale depuis le dossier de ce projet :

  `..\NZO - BLENDER EXTENSIONS REPOSITORY\nzo-repo.cmd bump <id> patch|minor|major`

- Cette commande synchronise aussi `bl_info["version"]` lorsqu'il existe encore. Ne modifier ni l'ID ni la partie descriptive du nom public sans demande explicite de migration.
- Avant de terminer une modification distribuée, exécuter au minimum `nzo-repo.cmd check`. Utiliser `smoke` pour une modification qui touche l'enregistrement, l'activation ou les dépendances.
- Préparer la version et les validations automatiquement fait partie du travail. Publier sur GitHub avec `publish` reste une action explicite : ne pas déployer sans demande de publication.
<!-- NZO_RELEASE_POLICY_END -->
