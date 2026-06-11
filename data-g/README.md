# data-g/ -- git-tracked data

Source-of-truth data files that must persist in GitHub live here.

The fleet-wide global gitignore ignores `data/` so ephemeral session artifacts
(transcripts, run logs, pickup state) never land in git. That is the right
default for throwaway state -- but it silently drops authoritative work product
too. Anything the runtime reads as canonical input -- roster files, corpora,
recipient lists, convergence configs -- belongs in `data-g/`, which the global
ignore does NOT match.

| Path | Tracked? | Use for |
|------|----------|---------|
| `data/`   | No (global gitignore) | Session transcripts, pickup state, throwaway run output |
| `data-g/` | Yes                   | Source-of-truth: rosters, corpora, configs the runtime depends on |

Rule of thumb: if losing the file on a machine wipe would hurt, it goes in
`data-g/`. (Convention established in AssemblyZero #1563.)
