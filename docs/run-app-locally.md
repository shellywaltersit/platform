## Overview

Before your app ever touches the cloud, you prove it works on your own machine, because "it runs on my laptop" is the minimum bar for "it should run anywhere."

## Why this matters

You used AI to help write your app. That's fine, and it's how a lot of real work gets done now. But AI writes code that *looks* right, and it can't run that code on your machine. It doesn't know which R version you have, which packages are installed, or where your data file lives.

Running locally is how you find out what the AI got wrong while the stakes are low. If you skip this and go straight to deploying, you'll be debugging three things at once (your code, your Terraform, and the cloud), and you won't know which one is broken.

The rule for this project: **nothing gets pushed to the deploy branch until it runs locally.**

## The mental model

When you run an app locally, your computer plays two roles at once:

| Role | What it means | Where you see it |
|---|---|---|
| **Server** | A program that waits for requests and sends back pages | Your terminal (logs and errors show up here) |
| **Client** | A browser that asks for the page and draws it | Your browser at `http://localhost:<port>` |

Two terms that get confused a lot:

- **`localhost`** means "this computer." Nobody else can reach it. That's the point. It's your private test environment.
- **Port** is like an apartment number on that computer. `localhost:8080` and `localhost:3838` are different apps living at the same address.

When something breaks, ask: is this a **server** problem (check the terminal) or a **client** problem (check the browser's developer console)? That one question cuts your debugging time in half.

---

## Pick your path

Your app is either an **R Shiny app** or a **D3 web page**. Follow the section that matches yours.

---

## Path A: R Shiny app

### 1. Check what you have installed

Open a terminal in VS Code (`` Ctrl+` `` or `` Cmd+` ``) and run:

```bash
R --version
```

If you get "command not found," R isn't installed or isn't on your PATH. Install it from [CRAN](https://cran.r-project.org/) and restart VS Code.

### 2. Find out which packages your app needs

Open your `app.R` (or `ui.R` / `server.R`) and look for every `library(...)` line at the top. That's your shopping list.

Ask your AI tool directly: *"List every R package this app uses, including ones only called with `::`."* Then check its answer against the code yourself. AI tools sometimes forget packages used as `dplyr::filter()` without a `library()` call.

### 3. Install the packages

Start R in the terminal:

```bash
R
```

Then install what you need (swap in your own list):

```r
install.packages(c("shiny", "dplyr", "ggplot2", "readr"))
```

> **Why we care about this list:** When you deploy, the container that runs your app starts with *nothing* installed. Whatever list you build here becomes the list you hand to the cloud. If it's incomplete locally, it'll be incomplete in production.

**Level up (optional):** Use [`renv`](https://rstudio.github.io/renv/) to record exact package versions in a lockfile. Run `renv::init()` once in your project folder, and `renv::snapshot()` whenever you add a package. This is the R equivalent of a `requirements.txt` and it's what professionals do.

### 4. Run the app

From the folder that contains `app.R`, still inside R:

```r
shiny::runApp(port = 8080)
```

You should see something like:

```
Listening on http://127.0.0.1:8080
```

Open that address in your browser. To stop the app, go back to the terminal and press `Ctrl+C` (or `Esc` if you're in an R console in VS Code).

### 5. Make it cloud-ready (do this now, thank yourself later)

Cloud services like Google Cloud Run tell your app which port to use through an environment variable named `PORT`. They also need your app to listen on all network interfaces, not just localhost. Change the bottom of your `app.R` to:

```r
# Cloud Run sets PORT for us. Locally it won't exist, so fall back to 8080.
# host = "0.0.0.0" means "accept connections from outside this machine",
# which a container needs. Locally it behaves the same as localhost.
port <- as.numeric(Sys.getenv("PORT", "8080"))
shinyApp(ui = ui, server = server, options = list(host = "0.0.0.0", port = port))
```

Now you can run it from the terminal (outside R) with:

```bash
Rscript app.R
```

Same app, same command, locally and in the cloud. That's the goal.

### Common Shiny errors

| Error in the terminal | What it's telling you | Fix |
|---|---|---|
| `there is no package called 'xyz'` | The package isn't installed on *this* machine | `install.packages("xyz")` |
| `could not find function "xyz"` | The package is installed but not loaded | Add `library(packagename)` at the top |
| `cannot open file 'data.csv': No such file or directory` | R is looking in a different folder than you think | Run from the folder containing `app.R`, and use relative paths like `data/data.csv`, never `C:/Users/you/...` |
| `Failed to create server` / port in use | Something else is already on that port (often your last run) | Stop the old one with `Ctrl+C`, or pick another port |

---

## Path B: D3 web page

### 1. Why you can't just double-click `index.html`

This is the number one D3 gotcha. If you open your file directly, the address bar shows `file:///...` and your chart is blank. Open the browser's developer tools (`F12`, then the **Console** tab) and you'll see an error mentioning **CORS** or **Failed to fetch**.

That error means: the browser refuses to let a page loaded from your hard drive read *other* files from your hard drive (like your CSV). It's a security rule, not a bug in your code. The fix is to serve the page through a tiny local web server, which is exactly what will happen in the cloud anyway.

### 2. Start a local web server

Pick **one** of these.

**Option 1: Python (already on most machines)**

In the VS Code terminal, from the folder that contains `index.html`:

```bash
python -m http.server 8080
```

On some Macs it's `python3` instead of `python`. You should see:

```
Serving HTTP on :: port 8080 ...
```

**Option 2: VS Code Live Server extension**

Install the **Live Server** extension, right-click `index.html`, and choose **Open with Live Server**. Bonus: it refreshes the browser every time you save.

### 3. Open it

Go to `http://localhost:8080` in your browser. Stop the server with `Ctrl+C` in the terminal.

### 4. Check how D3 is loaded

Look at the `<script>` tags in your `index.html`. AI tools usually load D3 from a CDN like this:

```html
<script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
```

That's fine. Just know it means you need an internet connection to see your chart, even locally. Also check the version number: D3 v5 and v7 code is **not** interchangeable (v7 changed how data loading works). If your AI mixed examples from different versions, things like `d3.csv(file, callback)` will silently fail. In v7 it's `d3.csv(file).then(data => ...)`.

### Common D3 errors (browser Console tab)

| Error | What it's telling you | Fix |
|---|---|---|
| `CORS policy` / `Failed to fetch` | You opened the file directly instead of through a server | Use step 2 above |
| `404 (Not Found)` for your CSV | The path in your code doesn't match where the file actually is | Paths are relative to `index.html`. Check spelling and capitalization. Linux servers in the cloud *are* case-sensitive even if your laptop isn't |
| `d3 is not defined` | The D3 script didn't load, or your code runs before it | Make sure the D3 `<script>` tag comes before yours |
| Chart is blank, no errors | Data loaded but came in as text, not numbers | CSV values arrive as strings. Convert with `+d.value` or `d3.autoType` |

---

## Working with AI when it breaks

You're going to hit errors. Good. Here's how to use AI well when you do:

1. **Read the error yourself first.** Copy the *exact* message. The first line usually tells you what's wrong, and the rest tells you where.
2. **Give the AI the whole picture.** Paste the exact error, the code it points to, and what you were doing (e.g., "I ran `Rscript app.R` from the project folder"). "It doesn't work" gets you a guess. An exact error gets you an answer.
3. **Change one thing at a time.** If the AI suggests five fixes, try one, rerun, and see what happens. Otherwise you won't know which one actually mattered, and you'll learn nothing.
4. **Ask "why," not just "fix it."** "Why did that error happen?" is how you get better at this. "Fix it" is how you end up stuck on the next one.

## Before you push: the local checklist

- [ ] The app starts from the terminal with no errors
- [ ] The page loads in the browser and the chart/app actually shows your data
- [ ] No errors in the terminal (Shiny) or browser Console (D3) while you click around
- [ ] All file paths are relative, with no `C:\Users\...` or `/Users/yourname/...`
- [ ] Your package list (Shiny) or script tags (D3) are complete
- [ ] Shiny only: the app reads `PORT` from the environment
- [ ] No passwords, API keys, or personal info in any file you're about to commit

If every box is checked, push to your feature branch and open your pull request.

## Questions to think about

- Your app works locally but fails in the cloud. List three things that are different between those two environments.
- Why does the cloud make your app read its port from an environment variable instead of hardcoding it?
- If a teammate cloned your repo tomorrow on a fresh laptop, what would they need to know to run it? Is that written down anywhere?

**Imagination spark:** What if you never had to install anything to run an app locally? Look up "dev containers" and think about what problem they solve.

