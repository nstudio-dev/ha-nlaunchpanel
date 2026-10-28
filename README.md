# NLaunchPanel pour Home Assistant

Les instances de votre [NLaunchPanel](https://github.com/nstudio-dev) comme
appareils de Home Assistant : leur état, leurs ressources, leurs sauvegardes,
et des boutons pour agir.

*Your NLaunchPanel instances as Home Assistant devices — English below.*

## Ce que vous obtenez

Un appareil par instance de l'organisation du jeton, avec :

| Entité | Type | Jeton |
|---|---|---|
| État (en marche, arrêtée, en échec…) | capteur | lecture |
| Processeur, mémoire | capteurs | lecture |
| Dernière sauvegarde réussie | capteur (diagnostic) | lecture |
| Image (nouvelle construction ou version disponible) | mise à jour | lecture ; installer : écriture |
| Marche / arrêt | interrupteur | écriture |
| Redémarrer, Sauvegarder maintenant, Redéployer | boutons | écriture |

Chaque nouvelle notification de la cloche du panel devient un événement
`nlaunchpanel_notification` (et, en option, une notification persistante) :

```yaml
trigger:
  - platform: event
    event_type: nlaunchpanel_notification
    event_data:
      severity: critical
action:
  - service: tts.speak
    data:
      message: "{{ trigger.event.data.title }}"
```

L'événement porte `id`, `kind`, `severity`, `title`, `body`, `link`, `created_at`.

## Installation

**Par HACS** : HACS › Dépôts personnalisés › `https://github.com/nstudio-dev/ha-nlaunchpanel`
(catégorie *Intégration*), installer, redémarrer Home Assistant.

**À la main** : copier `custom_components/nlaunchpanel` dans le dossier
`config/custom_components` de Home Assistant, puis redémarrer.

Puis : Paramètres › Appareils et services › Ajouter une intégration ›
**NLaunchPanel**, avec l'adresse du panel et un jeton d'API créé dans le panel
(Paramètres › Jetons d'API).

- Un jeton **lecture** donne les capteurs et l'état des mises à jour.
- Un jeton **écriture** ajoute les boutons, l'interrupteur et l'installation
  des mises à jour.

Les droits du jeton sont ceux de son propriétaire, relus par le panel à chaque
appel : un membre retiré de l'organisation perd l'accès aussitôt.

## Fonctionnement

- Un tour toutes les 60 secondes : la liste des instances, puis, pour chacune,
  ses mesures, ses sauvegardes et l'état de son image (quatre appels en
  parallèle au plus), et la cloche.
- Panel injoignable : les entités passent « indisponibles », rien n'est perdu.
- Jeton refusé (expiré, révoqué) : Home Assistant demande un nouveau jeton.
- Les alertes demandent un panel qui ouvre sa cloche aux jetons d'API
  (octobre 2026) ; sur un panel plus ancien, les capteurs et les boutons
  marchent, les alertes attendent sa mise à jour.

---

## English

One device per instance of the token's organisation: state, processor,
memory, last backup, image update; with a **write** token, an on/off switch and
Restart / Back up now / Redeploy buttons. Each new notification of the panel's
bell fires a `nlaunchpanel_notification` event (optionally a persistent
notification too).

Install through HACS (custom repository
`https://github.com/nstudio-dev/ha-nlaunchpanel`, category *Integration*) or by
copying `custom_components/nlaunchpanel`, restart Home Assistant, then add the
**NLaunchPanel** integration with the panel address and an API token
(panel: Settings › API tokens).
