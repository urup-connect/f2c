# Components

Reusable components live here, grouped by domain: `src/components/<Domain>/<Name>.tsx`
with its test colocated as `<Name>.test.tsx`.

Built and tested in isolation before being wired into a route — see rule 3 in `CLAUDE.md`.
Props in, events out: no data fetching, no route awareness, no global state.
