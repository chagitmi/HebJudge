# Installing HebJudge

HebJudge runs on your own computer. The interface opens in your browser, and your agents, scans and results stay in the folder you run it from. Only two things leave your computer: the attack messages, which go to the agent you test, and each exchange, which goes to OpenAI to be judged with your own API key.

[עברית](INSTALL.he.md)

## What you need

- **Python 3.11 or newer.**
- **An OpenAI API key**, for the judge. Scans are billed to your OpenAI account; a quick scan costs about $0.05, and the cost is shown before anything is sent.
- **An agent you own, or have permission to test**, in a test environment. To try HebJudge first, use the free example agent.

## 1. Install Python (skip if you have it)

Check in a terminal (on Windows: PowerShell):

```bash
python --version
```

If it shows 3.11 or newer, go to step 2. Otherwise:

- **Windows:** download Python from [python.org/downloads](https://www.python.org/downloads/). In the first screen of the installer, tick **Add python.exe to PATH**, then **Install Now**. Close and reopen PowerShell afterwards.
- **macOS:** download from [python.org/downloads](https://www.python.org/downloads/), or `brew install python`.
- **Linux:** use your distribution's package manager.

## 2. Install HebJudge

Choose a folder for your work, for example `Documents\HebJudge`, open a terminal in it, and run:

```bash
python -m venv .venv
```

Activate it:

- Windows (PowerShell): `.\.venv\Scripts\Activate.ps1`
- macOS / Linux: `source .venv/bin/activate`

If PowerShell refuses to run the script, run once: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`, then activate again.

Then:

```bash
pip install hebjudge
hebjudge init
```

`hebjudge init` copies the example agents into `examples/` in this folder.

## 3. Add your API key

Create a key at [platform.openai.com/api-keys](https://platform.openai.com/api-keys). Then either:

- open the interface (step 4) and paste it under **Settings**, or
- run `hebjudge key set` and paste it (it is not shown while you type).

The key is saved in `~/.hebjudge/config.env`, readable by your user only, and never in your project folder. `hebjudge key test` checks it at no cost.

## 4. Open the interface

```bash
hebjudge ui
```

Your browser opens at `http://127.0.0.1:8770`. If it does not, copy that address into the browser. Stop the interface with **Ctrl+C** in the terminal.

Next time, open a terminal in the same folder, activate the environment (step 2), and run `hebjudge ui`.

## 5. First steps in the interface

1. **Agents:** run **Test connection** on *Toy agent*. It is free and needs no key.
2. **Scan:** pick the toy agent and look at the messages that would be sent. A quick scan of it costs about $0.04 for the judge.
3. **Your own agent:** **New agent**, then fill in how to connect and its profile: what it may do, what is secret, what is forbidden, and a few legitimate requests.

## Updating

```bash
pip install --upgrade hebjudge
```

## Troubleshooting

| Problem | Fix |
|---|---|
| `hebjudge` is not recognized | The environment is not active: run the activate command from step 2 |
| `python` is not recognized (Windows) | Reinstall Python with **Add python.exe to PATH**, or use `py` instead of `python` |
| The browser opens Edge instead of Chrome | The interface opens your default browser; copy the address into Chrome, or change the default in Windows Settings |
| Port 8770 is busy | `hebjudge ui --port 8771` |
| "Missing API key" | Add it under Settings, or `hebjudge key set` |
| The key does not work | Check that it was copied in full, and that the OpenAI account has credit |
