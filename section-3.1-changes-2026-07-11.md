# 498 working.md — Section 3.1 change record (2026-07-11)

This file records the **current uncommitted changes** in `498 working.md` that fall within **Section 3.1** (`# 3.1` up to (but not including) the next `# x.y` heading), as compared to `HEAD`.

- Repo base: `4b5659401c81f30c4311047c1b192bb54beb22c0`
- Source file: `498 working.md`
- Section 3.1 line ranges (detected automatically):
  - `HEAD`: lines 54–264
  - working tree: lines 54–260

## How to regenerate (exact)

```bash
# Extract section 3.1 from HEAD and from the working tree, then diff.
python3 - <<'PY'
import re, subprocess, pathlib

def get_text(ref=None):
    if ref is None:
        return pathlib.Path('498 working.md').read_text(encoding='utf-8')
    return subprocess.check_output(['git','show',f'{ref}:498 working.md']).decode('utf-8',errors='replace')

def section_range(text, title='3.1'):
    lines=text.splitlines()
    start=None
    end=None
    pat=re.compile(rf'^#\s+{re.escape(title)}\b')
    for i,l in enumerate(lines,1):
        if pat.match(l):
            start=i
            break
    if start is None:
        raise SystemExit('Section not found')
    for i in range(start+1, len(lines)+1):
        if re.match(r'^#\s+\d+\.\d+\b', lines[i-1]):
            end=i
            break
    if end is None:
        end=len(lines)+1
    return start,end

def slice_text(text, start, end):
    lines=text.splitlines(True)
    return ''.join(lines[start-1:end-1])

head = get_text('HEAD')
work = get_text(None)
h0,h1 = section_range(head,'3.1')
w0,w1 = section_range(work,'3.1')
path_head='section_3_1_HEAD.md'
path_work='section_3_1_WORKTREE.md'
open(path_head,'w',encoding='utf-8').write(slice_text(head,h0,h1))
open(path_work,'w',encoding='utf-8').write(slice_text(work,w0,w1))
print('HEAD', (h0,h1-1), 'WORKTREE', (w0,w1-1))
PY

diff -u section_3_1_HEAD.md section_3_1_WORKTREE.md
```

## What changed (summary)

- Removed Section 3.1’s explicit ownership bullets for `NFS8` (fault recovery acceptance spec) and `NFS9` (line-rate ingest throughput acceptance spec).
- Updated the “Decision 1” board paragraph to cite the board manual as `[17]` instead of the placeholder `(REF-3)`.
- Updated “Decision 2” text to replace the `OPEN` TEMAC latency placeholder with a bounded-assumption reference to a product guide `[16]` (details are in the Section 3.1 diff).
- In Table 3.1.4, removed the clause tying `seq_num` to throughput-test loop boundaries; it now only mentions drop accounting (`NFS2`).
- In the observability/counters table, generalized “NFS2/NFS8 observability” to “NFS2 / fault-path observability”.
- Renamed `3.1.4.1` from “Line-rate throughput (NFS9)” to “Line-rate throughput analysis” and adjusted the text to remove a formal acceptance target while keeping the wire-ceiling analysis.
- Removed `NFS8`/`NFS9` rows from the Section 3.1 verification-summary table at the end of the section.

