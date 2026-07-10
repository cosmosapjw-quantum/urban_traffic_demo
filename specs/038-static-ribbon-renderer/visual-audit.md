# PR38 Diagnostic Visual Audit

## Procedure

- Generated full and roads-only seed-44 HTML artifacts.
- Rendered 1440x1100 PNGs with local headless Chrome.
- Inspected both PNGs at original resolution.

## Confirmed Improvements

- `5,642` directed links reduce to `2,821` physical road ribbons.
- Road classes, repair links, bridges, medians, and shoulders are distinguishable.
- One uniform `0.1624833885 px/m` transform preserves horizontal/vertical scale.
- Layer isolation removes POI and zone clutter during road-structure review.

## Remaining Structural Defects

- The generated city still reads as an outer rectangular scaffold joined to
  several dense local clusters rather than a continuous urban street fabric.
- Long diagonal collectors cross large undeveloped gaps and create visually
  implausible direct connections.
- Central clusters contain many crossing centerlines and weak block structure.
- POIs overwhelm the full composite and should remain independently reviewable.

These are generator/topology defects, not ribbon-renderer defects. The images
are diagnostic smoke artifacts and do not establish city realism or validity.
