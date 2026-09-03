# Contexte — Projet portfolio NatCat (Ilyas Hammouti)

## Qui je suis, en une phrase
Étudiant en master Dynarisk (Dynamiques des milieux et risques, Paris 1 Panthéon-Sorbonne), en préparation d'un stage de fin d'études (M2, ~février 2027) dans une réassurance ou assurance en Suisse (cible prioritaire : Swiss Re, Zurich, rôle geospatial risk). Objectif personnel : m'installer durablement à Zurich ("SUISSE 2027").

## Niveau technique actuel — important à savoir avant de coder quoi que ce soit
- Je ne sais pas coder. Ni Python, ni SQL, ni rien.
- Je veux apprendre en autonomie, avec une logique Pareto stricte : 20% de l'effort pour 80% du résultat utile. Je ne cherche pas à devenir développeur, je cherche à sortir du lot par rapport à un master de géographie classique.
- Je maîtrise en revanche QGIS, ArcGIS Pro, MicroStation, et j'ai déjà produit des cartes d'analyse spatiale sérieuses (voir plus bas).
- R Studio arrivera nativement au semestre prochain via mon master (stats appliquées).
- Ressource d'apprentissage Python identifiée et validée : cours GEOG 312 du Dr Qiusheng Wu (Univ. Tennessee, gratuit, public, exécutable via Colab/Binder) — https://gispro-fall26.gishub.org/. Wu est aussi le créateur de `geemap`, la librairie Python qui connecte à Google Earth Engine.
- Sélection Pareto déjà arrêtée dans ce cours : (1) fondamentaux Python — variables, boucles, fonctions, Pandas ; (2) GeoPandas + Rasterio ; (3) geemap. Le reste (Xarray, WhiteboxTools, MapLibre, Solara, Sedona, DuckDB) est secondaire, à survoler seulement si le temps le permet.

## Le projet vitrine — pourquoi et quoi

### Le "pourquoi", posé clairement après discussion
Ce n'est pas juste "une ligne de CV". Le but est de démontrer concrètement, à un recruteur du secteur assurance/réassurance, une compréhension réelle de la logique d'un modèle catastrophe naturelle (cat model), et une capacité à produire des diagnostics chiffrés exploitables — pas juste de jolies cartes de géographe.

### Ce que j'ai déjà produit (le point de départ, pas un début à zéro)
J'ai réalisé et publié sur LinkedIn une carte "Et si la crue de 1910 se reproduisait aujourd'hui ?" sur Paris/petite couronne, sous QGIS, croisant :
- une couche d'aléa (zone inondée simulée, source : Direction de la Prévention et de la Protection - Ville de Paris)
- une couche d'exposition (valeur foncière du bâti via DVF, population potentiellement affectée, infrastructures : 32,4 km d'autoroute, 115 stations de métro/RER)
- Résultat : 11 814 ha inondés, ~2,57M personnes potentiellement affectées, 825,7 milliards € de bâti affecté.

Ce travail est structurellement un Hazard × Exposure, **sans la couche Vulnerability et sans calcul de Loss** (perte estimée). C'est exactement cette brique manquante que le projet vitrine doit ajouter.

### La logique du cat model (comprise et validée dans la discussion précédente)
**Hazard × Exposure × Vulnerability = Loss**
- Hazard : où/quand/intensité de l'événement
- Exposure : ce qui est exposé et sa valeur (déjà fait, cf. carte 1910)
- Vulnerability : taux de dommage selon intensité et type d'élément exposé (brique manquante)
- Loss : résultat financier final — PAS juste "valeur exposée", une vraie perte estimée

Le NatCat Modelling Engine de Swiss Re (référence officielle consultée) confirme cette même structure en 4 modules (Hazard, Vulnerability, Exposure, + un 4e module "Insurance conditions" — franchises/plafonds/exclusions — que je n'ai pas vocation à reproduire, c'est la sophistication propriétaire de Swiss Re, pas mon objectif).

### L'outil retenu pour combler la brique manquante : CLIMADA
- Framework Python open-source développé par ETH Zurich (Weather and Climate Risks group).
- Intègre nativement Hazard + Exposure + Vulnerability → Loss. Fonctions de vulnérabilité déjà calibrées scientifiquement et fournies avec l'outil (pas besoin de les coder moi-même).
- Couverture "core" (mature) : cyclone tropical, tempêtes de vent, séisme, inondation fluviale, sécheresse/risque agricole, feu de forêt.
- Module "petals" (plus expérimental) : glissement de terrain notamment.
- Pas de module volcanique natif — écarté du scope pour l'instant (pas de fonctions de vulnérabilité prêtes, hors budget Pareto).
- Signal de crédibilité fort : EIOPA (régulateur assurance européen) a développé une interface simplifiée sur CLIMADA ("CLIMADA-app") destinée aux PME d'assurance — donc pas qu'un outil académique, un outil poussé activement dans l'industrie.
- Repo GitHub : `CLIMADA-project/climada_python`
- Installation recommandée officiellement : via **conda/mamba** (PAS pip — pip échoue à cause de la dépendance GDAL qui nécessite des bibliothèques système, voir plus bas).

### Séquencement du projet (décidé — éviter de s'éparpiller)
**Phase 1 (à faire maintenant)** : un seul péril, le pipeline complet, bien fait. Péril choisi : **inondation** (cohérence avec la carte 1910 déjà produite, module CLIMADA mature, indice spectral NDWI est le plus simple pour débuter en télédétection).
- Reprendre la logique de la carte 1910, mais cette fois calculer une vraie perte estimée via CLIMADA (pas juste une valeur exposée).
- Documenter proprement sur GitHub une fois que ça tourne.

**Phase 2 (plus tard, seulement si Phase 1 est solide)** : extension au feu de forêt (indice NBR, aussi mature dans CLIMADA, sujet à forte résonance médiatique récurrente l'été).

**Volcanique/sismique** : mis de côté, ou traité uniquement côté détection factuelle (télédétection, sans couche de perte financière).

### Le deuxième volet technique, complémentaire : détection d'événements réels (pas seulement probabiliste)
CLIMADA sert surtout à la modélisation probabiliste (pricing, périodes de retour). Il existe un deuxième métier réel en cat modeling : la détection factuelle d'un événement qui vient de se produire, via télédétection satellite (comparaison d'indices spectraux avant/après). Référence identifiée : **HazMapper** (Scheip & Wegmann, NC State, publié dans NHESS/AGU), qui utilise le rdNDVI pour détecter glissements de terrain, feux, coulées pyroclastiques, etc. Code source sous licence "research-only" (pas de réutilisation commerciale, mais étude/inspiration libres). L'écosystème `geemap` (Qiusheng Wu / opengeos) fournit 360+ notebooks d'exemples GEE en accès libre, utile comme base d'inspiration.

Distinction claire à garder en tête :
- **Toolbox GEE (type HazMapper)** = event response — détection rapide d'un événement réel déjà survenu.
- **CLIMADA** = pricing/projection — simulations probabilistes pour calculer un risque et une prime.
Ce sont deux métiers réels et complémentaires chez un réassureur, pas deux outils redondants.

## Ce qu'on a tenté de faire avant de passer la main à Claude Code
Tentative d'installation de CLIMADA via `pip install climada --break-system-packages` dans un environnement bac à sable (sandbox Claude.ai) : échec, car CLIMADA dépend de GDAL qui nécessite des bibliothèques système natives non disponibles dans ce sandbox (pas de conda-forge accessible, réseau restreint à une whitelist de domaines). Tentative de contournement via l'API cliente Python de CLIMADA (`climada.util.api_client.Client`) : ce n'est PAS une API web indépendante, c'est un module interne au package CLIMADA qui télécharge des fichiers `.hdf5` puis les charge dans des objets `climada.Hazard` / `climada.Exposures` — donc ça ne contourne pas le besoin d'installer CLIMADA complet avec GDAL.

**Conclusion : l'installation doit se faire dans un vrai environnement local (ou une machine que Claude Code contrôle réellement), pas dans le sandbox web Claude.ai.** C'est pour ça qu'on passe la main à Claude Code maintenant.

## Ce que je veux que Claude Code fasse concrètement (voir prompt séparé)
1. Installer CLIMADA correctement (mamba/conda-forge, pas pip).
2. Faire tourner un premier tutoriel officiel simple (idéalement lié à l'inondation, ou à défaut le tutoriel le plus simple disponible type LitPop + tropical cyclone pour valider que l'installation fonctionne).
3. M'expliquer concrètement ce que ça produit : quel type d'objet, quelle sortie visuelle, quel ordre de grandeur de résultat — en partant du principe que je ne sais pas coder, donc en vulgarisant sans être condescendant.
4. Poser les bases d'un notebook orienté vers MON objectif : reproduire un scénario proche de ma carte crue 1910 (Paris/Île-de-France, inondation), avec une vraie exposition (bâti) et une vraie fonction de vulnérabilité CLIMADA, pour obtenir une perte estimée en euros — pas juste une valeur exposée.

## Ce qui n'est PAS demandé à ce stade
- Pas besoin de coder les fonctions de vulnérabilité moi-même (CLIMADA les fournit).
- Pas besoin de couvrir plusieurs périls d'un coup (focus strict inondation pour l'instant).
- Pas besoin de reproduire le module "Insurance conditions" de Swiss Re (franchises, plafonds) — hors scope.
- Pas la peine de me proposer une architecture logicielle complexe (cloud, API web, etc.) — c'est un projet portfolio individuel, pas un produit à déployer.
