# Files that belong in GitHub

Commit viewer source, HTML/JavaScript templates, installation scripts,
dependency lists, tests, documentation, and licenses. The Berry Camp fixture
contains licensed room identifiers and ordering metadata, not Celeste maps or
artwork; keep its attribution and license alongside it.

Keep these local:

| Local files | Why they stay out of GitHub |
| --- | --- |
| `.venv/`, `.install-test/`, `venv/`, `env/` | Installed dependencies and machine-specific environments. |
| `outputs/`, `previews/` | Generated browsers, rendered images, map snapshots, and verification artifacts. |
| `celeste_gameplay_viewer/assets/sprites/*` except `README.md` | Game artwork extracted from the user's installed copy of Celeste, including its local manifest. |
| `*.bin`, `*.data` | Celeste maps and packed game assets. |
| Python bytecode, caches, build output, coverage output, logs | Reproducible development artifacts. |
| `.env*` except `.env.example`, keys, credentials, editor settings | Private or machine-specific configuration. |

Source templates under `assets/` and `tools/prototype-assets/` are maintained
code and should be committed. Generated HTML under `outputs/` should not.
The installer downloads `loenn-mcp` separately; its installed source is not
part of this repository.

## Checks before pushing

`.gitignore` prevents ordinary staging. Git still permits force-adding ignored
files and does not stop tracking files already committed. The additional check
examines the index and all reachable Git history against the current rules:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/check_repository.ps1
```

Enable it as a pre-push hook in each Windows checkout:

```powershell
Copy-Item tools/pre-push .git/hooks/pre-push
```

The hook fails closed if the check cannot run. It can be bypassed deliberately,
so it does not guarantee that arbitrary credentials can never be published.
It checks file policy, not secrets embedded in otherwise valid source files.
Do not put real credentials in source or `.env.example`.

The hook adds a check to the existing workflow:

```text
local files -> .gitignore -> Git index/commits -> pre-push check -> GitHub
                                                 |
                                                 +-> excluded path: stop
```

An audit on 2026-10-11 fetched GitHub's only published branch, `main`, at
`7f08fe0a349c7583070d6545f4c14fde07222743`. All three published commits
were checked. None contained excluded game assets, maps, generated output,
environments, or credential files; no history rewrite was needed.

See Git's official [ignore rules](https://git-scm.com/docs/gitignore) and
[hook behavior](https://git-scm.com/docs/githooks).
