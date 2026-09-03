# API optiFamily — référence technique (contributeurs)

> **Public cible** : développeurs / contributeurs du projet.  
> Pour installer et utiliser l’intégration : voir le [README](../README.md).
>
> Documentation communautaire non officielle, basée sur l’observation des requêtes du portail.  
> Cette intégration est un projet open-source non officiel et n'est ni affiliée à, ni soutenue par THEMISTO CONSEIL / optiCrèche.
>
> **Tous les identifiants, noms et tokens ci-dessous sont fictifs.**  
> Placeholders : `EMAIL`, `PASSWORD`, `ACCESS_TOKEN`, `REFRESH_TOKEN`, `CRECHE_ID`, `ENFANT_ID`, `USER_ID`, `MESSAGE_ID`, `CRENEAU_ID`.

---

## 1) Vue d'ensemble

| Élément | Valeur |
|---|---|
| Base URL | `https://back.opticreche.fr` |
| Scope | `FAMILLE` |
| Auth | `Authorization: Bearer ACCESS_TOKEN` |
| Format | JSON |
| Mode intégration HA | **Lecture seule** |

Objectifs couverts : compte, enfants, planning, transmissions, albums, actualités, messages, documents, facturation.

---

## 2) Flux d'authentification

### Étape A — pré-login

- **Méthode / chemin** : `POST /auth/pre-login`
- **Auth** : non
- **But** : initialiser le contexte et lister la/les crèche(s) liées au compte

**Request**

```json
{
  "username": "EMAIL",
  "scope": "FAMILLE"
}
```

| Paramètre | Type | Description |
|---|---|---|
| `username` | string | Adresse e-mail du parent |
| `scope` | string | Toujours `FAMILLE` pour optiFamily |

**Response observée**

```json
[
  {
    "id": "CRECHE_ID",
    "libelle": "NOM_CRECHE"
  }
]
```

- Une crèche → un objet dans le tableau.
- Plusieurs crèches → plusieurs objets (`id` + `libelle`).
- L’intégration utilise cette réponse pour la découverte / sélection de `crecheId`.

### Étape B — login

- **Méthode / chemin** : `POST /auth/login`
- **Auth** : non

**Request**

```json
{
  "crecheId": "CRECHE_ID",
  "password": "PASSWORD",
  "scope": "FAMILLE",
  "username": "EMAIL"
}
```

| Paramètre | Type | Description |
|---|---|---|
| `crecheId` | integer / string numérique | Identifiant de la crèche |
| `password` | string | Mot de passe |
| `scope` | string | `FAMILLE` |
| `username` | string | E-mail |

**Response observée (`LoginResponse`)**

```json
{
  "status": "success",
  "messages": null,
  "accessToken": "ACCESS_TOKEN",
  "refreshToken": "REFRESH_TOKEN"
}
```

### Étape C — requêtes authentifiées

Tous les endpoints sous `/api/auth/v3/...` (et `POST .../remove-fcm-token`) utilisent :

```text
Authorization: Bearer ACCESS_TOKEN
Content-Type: application/json
Accept: application/json
```

### Étape D — refresh token

- **Méthode / chemin** : `POST /auth/refresh`
- **Auth** : non (le refresh token est dans le body)
- Contrôleur observé : `LoginControllerV3.refresh(RefreshRequest)`
- Retour attendu : `LoginResponse`

**Request (corps obligatoire)**

```json
{
  "refreshToken": "REFRESH_TOKEN"
}
```

Sans body, le backend répond `400` :

```json
{
  "status": 400,
  "error": "Bad Request",
  "exception": "org.springframework.http.converter.HttpMessageNotReadableException",
  "message": "Required request body is missing: ... LoginControllerV3.refresh(RefreshRequest)",
  "path": "/auth/refresh"
}
```

**Response attendue**

```json
{
  "accessToken": "ACCESS_TOKEN",
  "refreshToken": "REFRESH_TOKEN"
}
```

(`status` / `messages` peuvent aussi être présents, comme au login.)

### Étape E — expiration / stratégie HA

1. Appel API → `401`
2. Tentative `POST /auth/refresh`
3. Si échec → `pre-login` + `login` complets
4. Nouvelle tentative de l’appel d’origine (une seule fois)

---

## 3) Multi-crèches et multi-enfants

### Multi-crèches

- Un compte peut exposer plusieurs entrées via `/auth/pre-login`.
- Dans Home Assistant : **une config entry = une crèche**.
- On peut ajouter l’intégration plusieurs fois (une fois par crèche).
- Chaque instance a ses tokens et sa liste d’enfants.

### Multi-enfants

- `GET .../enfants` renvoie `1..N` enfants pour la crèche active.
- Pour chaque enfant : planning du mois, transmissions du jour, albums.
- Capteurs HA : **1 appareil par enfant** + capteurs agrégés au niveau compte.

---

## 4) Catalogue des endpoints

| Méthode | Endpoint | Auth | État |
|---|---|---|---|
| `POST` | `/auth/pre-login` | ❌ | ✅ Observé |
| `POST` | `/auth/login` | ❌ | ✅ Observé |
| `POST` | `/auth/refresh` | ❌ (body) | ✅ Observé |
| `GET` | `/api/auth/v3/me` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/logout` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/enfants` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/enfant/{id}/planning/{year}/{month}` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/enfant/{id}/transmissions/{date}` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/enfant/{id}/albums` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/actualites/from/{from}/to/{to}` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/messages` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/documents/creche/{crecheId}` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/facturation` | ✅ Bearer | ✅ Observé |
| `GET` | `/api/auth/v3/opti-family/profil` | ✅ Bearer | ✅ Observé (sensible, **non utilisé** par HA) |
| `POST` | `/api/auth/v3/opti-family/remove-fcm-token` | ✅ Bearer | ✅ Observé (non utilisé par HA) |

---

## 5) Détail des payloads

### `GET /api/auth/v3/me`

Retourne le compte connecté et la crèche courante.

```json
{
  "id": "USER_ID",
  "nom": "NOM_FAMILLE",
  "type": "FAMILLE",
  "multiStructure": false,
  "admin": false,
  "transverse": false,
  "creche": {
    "id": "CRECHE_ID",
    "nom": "NOM_CRECHE",
    "adresse": "ADRESSE"
  },
  "defaultRoute": null
}
```

### `GET /api/auth/v3/opti-family/enfants`

```json
[
  {
    "id": "ENFANT_ID",
    "libelle": "PRENOM"
  }
]
```

### `GET /api/auth/v3/opti-family/enfant/{enfantId}/planning/{année}/{mois}`

Exemple : `/enfant/ENFANT_ID/planning/2026/9`

```json
{
  "label": "Planning de septembre 2026",
  "previous": "2026-08",
  "next": "2026-10",
  "semaines": [
    {
      "numero": "S36",
      "journees": [
        {
          "label": "J 3",
          "date": "2026-09-03",
          "visible": true,
          "canAdd": true,
          "creneaux": [
            {
              "type": "regulier",
              "id": "CRENEAU_ID",
              "label": "07:45 - 18:45",
              "details": "",
              "editable": false
            }
          ]
        }
      ]
    }
  ]
}
```

| Champ | Description |
|---|---|
| `label` | Libellé du mois |
| `previous` / `next` | Mois adjacent (`YYYY-MM`) |
| `semaines[].numero` | Numéro de semaine |
| `journees[].date` | Date ISO |
| `journees[].visible` | Jour appartenant au mois demandé |
| `journees[].canAdd` | Créneau ajoutable (suggère des endpoints d’écriture) |
| `creneaux[].type` | Ex. `regulier`, `fermeture` |
| `creneaux[].label` | Horaires / libellé |
| `creneaux[].editable` | Créneau modifiable |

### `GET /api/auth/v3/opti-family/enfant/{enfantId}/transmissions/{date}`

- `date` au format `YYYY-MM-DD`
- Peut renvoyer `[]` s’il n’y a aucune transmission

### `GET /api/auth/v3/opti-family/enfant/{enfantId}/albums`

- Liste d’albums / photos ; peut être `[]`

### `GET /api/auth/v3/opti-family/actualites/from/{from}/to/{to}`

| Paramètre | Description |
|---|---|
| `from` | Offset de début |
| `to` | Offset / borne de fin |

```json
{
  "total": 0,
  "actualites": []
}
```

### `GET /api/auth/v3/opti-family/messages`

```json
[
  {
    "id": "MESSAGE_ID",
    "sender": true,
    "message": "CONTENU",
    "date": "2026-09-03 17:02:13",
    "vu": false
  }
]
```

| Champ | Description |
|---|---|
| `sender` | `true` si envoyé par l’utilisateur connecté |
| `vu` | Message lu ou non |

### `GET /api/auth/v3/opti-family/documents/creche/{crecheId}`

- Documents de la crèche ; peut être `[]`

### `GET /api/auth/v3/opti-family/facturation`

- Éléments de facturation ; peut être `[]`

### `GET /api/auth/v3/opti-family/profil` ⚠️

Profil famille **très sensible**. Champs possibles (ne jamais logger ni exposer en entités HA) :

- `parent1` / `parent2` (civilité, nom, prénom, email, mobile, profession, employeur…)
- adresse, code postal, ville, téléphones
- `nomAllocataire`, `numeroAllocataire`
- assurance, `prelevementSEPA`
- `regimeAffiliation`, `reservataire`
- `enfants[]`
- `mandats[]` avec `iban`, `bic`, `rum`, titulaire, date
- `otp`, `shouldUpdatePassword`
- `creche` (id, nom, téléphone, mail)

**L’intégration Home Assistant n’appelle pas cet endpoint.**

### `POST /api/auth/v3/opti-family/remove-fcm-token`

```json
{
  "token": "FCM_TOKEN"
}
```

- Réponse observée : **corps vide**
- Non utilisé par l’intégration HA

### `GET /api/auth/v3/logout`

- Pas de body
- Réponse observée : **corps vide**
- Invalide la session côté serveur

---

## 6) Endpoints d’écriture (non utilisés)

Les flags `canAdd` / `editable` du planning suggèrent des `POST` / `PUT` / `DELETE` côté portail.

Pour cette intégration HACS :

- **aucune écriture** n’est implémentée
- sens du flux : OptiFamily → Home Assistant uniquement

---

## 7) Gestion des erreurs

| Code | Comportement recommandé |
|---|---|
| `200` / `204` | Succès (parfois sans corps) |
| `400` | Payload invalide |
| `401` | Refresh puis login |
| `403` | Accès refusé |
| `5xx` | Indisponibilité backend |

Règles de journalisation :

- messages synthétiques uniquement
- jamais de réponse API complète
- tronquer les corps d’erreur (ex. 200 caractères max)

---

## 8) Sécurité & anonymisation

Ne jamais committer / publier / logger :

- mot de passe
- `accessToken` / `refreshToken`
- token FCM
- IBAN / BIC / RUM
- numéro allocataire, coordonnées réelles
- IDs réels de compte / enfant / crèche dans issues ou captures publiques

Toujours remplacer par : `EMAIL`, `PASSWORD`, `ACCESS_TOKEN`, `CRECHE_ID`, `ENFANT_ID`, etc.

---

## 9) Correspondance avec l’intégration Home Assistant

| Besoin HA | Endpoint |
|---|---|
| Auth | `/auth/pre-login`, `/auth/login`, `/auth/refresh` |
| Métadonnées compte / crèche | `/me` |
| Liste enfants | `/enfants` |
| Présence / créneaux | `/enfant/{id}/planning/...` (+ plateforme `calendar`) |
| Transmissions | `/enfant/{id}/transmissions/{date}` |
| Albums | `/enfant/{id}/albums` |
| Messages non lus (crèche / moi) | `/messages` (`sender`) |
| Actualités / docs / factures | endpoints correspondants (compteurs) |

Non utilisés volontairement : `/profil`, `remove-fcm-token` (hors besoin domotique / trop sensible).

Persistance HA :

- `creche_id`, `creche_name`, liste `enfants` → config entry
- tokens → store local par `entry_id`
- polling défaut : 1800 s (30 min), mini 300 s, maxi 7200 s

---

## 10) Limites connues / à confirmer

- Schémas JSON variables selon crèches / versions du portail
- Contenu exact d’un succès `/auth/refresh` encore partiellement caractérisé
- Structures détaillées de `actualites[]`, `documents[]`, `facturation[]`, `albums[]` selon les comptes
- Endpoints d’écriture planning non cartographiés
- Endpoints de détail unitaire (message / document) non confirmés
- Durée de vie / rotation exacte des tokens non documentée officiellement

---

## 11) Récapitulatif

| Sujet | État |
|---|---|
| Auth pre-login / login / refresh | Observé |
| Lecture famille / enfants / planning | Observé |
| Multi-crèches | Géré via multi-instance HA |
| Multi-enfants | Géré nativement |
| `/profil` | Observé, exclu de HA |
| Écriture planning | Non utilisé |
| Anonymisation des exemples | Obligatoire |
