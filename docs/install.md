# Install

JamShoot Studio is not on PyPI; install it from GitHub. It needs Python 3.11 or
newer (`python3 --version`) and an installed sans-serif font; see
[Rendering](rendering.md#fonts). Node.js is only for [development](development.md).

## Studio on macOS or Linux

```sh
git clone https://github.com/jamshoot-apps/jamshoot-studio.git
cd jamshoot-studio
./studio
```

`./studio` creates `.venv`, installs what is missing, starts Studio and opens it in
the browser. It passes its options to `jamshoot studio`, for example
`./studio --port 0`. Continue with [Studio](studio.md).

## Manual install and Windows

From the cloned folder:

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[web]'
jamshoot studio --open
```

On Windows PowerShell, use `py -m venv .venv` and `.venv\Scripts\Activate.ps1`.
The `web` extra adds the browser editor; without it only the CLI is installed.
`python -m jamshoot` works wherever `jamshoot` does.

## CLI in CI or for an agent

Install a tagged release, without the editor:

```sh
python -m pip install "git+https://github.com/jamshoot-apps/jamshoot-studio@v1.0.0"
sudo apt-get install --yes --no-install-recommends fonts-dejavu-core  # Linux runners
jamshoot validate screenshots/project.json --json
jamshoot render screenshots/project.json --out build/screenshots --json
```

`render` needs an output folder that does not exist yet. See [CLI](cli.md) for every
command and its JSON output.
