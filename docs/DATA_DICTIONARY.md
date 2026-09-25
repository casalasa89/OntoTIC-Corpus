# Data dictionary

## Corpus metadata

The repository-safe corpus table excludes `texto_modelado`. Key fields include document identifier, actor, actor type, title, year, source, URL, DOI, validation decision, modelability status, semantic relevance, SHA-256 hash, and source-file reference.

## Actor profiles

Each evaluable actor has four adjusted proportions that sum to one:

- `investigación`
- `desarrollo`
- `mercadeo`
- `difusión_transferencia`

`documentos_modelables_lda = 0` means that the actor is non-evaluable. It does not mean zero organizational capability.

## Dyadic matrix

The 43 actors produce 903 unordered pairs. The file contains:

- 741 evaluated dyads;
- 162 non-evaluable dyads;
- reciprocal gap coverage;
- joint coverage;
- redundancy;
- auxiliary weighted Jaccard similarity;
- profile distance;
- potential complementarity; and
- evidence-adjusted priority.

The score represents structural potential. It is not evidence of observed collaboration, realized complementarity, causal synergy, or coopetition.
