# Changelog

Toutes les modifications notables de ce projet seront documentées dans ce fichier.

Le format s'inspire de [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/),
et ce projet adhère au [Versionnement Sémantique](https://semver.org/lang/fr/).

## [Unreleased]

## [1.0.1] - 2026-09-03

### Fixed
- Crash au setup : `persisted_enfants` manquant dans `__slots__` de `OptieFamilyData`

### Added
- Intervalle de polling configurable (défaut 30 min, mini 5, maxi 120)
- Capteur diagnostic « Dernier rafraîchissement »
- Coverage tests à 100 %

## [1.0.0] - 2026-09-03

### Added
- Première version publique
