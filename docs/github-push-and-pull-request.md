# Pushing Your Code to GitHub and Opening a Pull Request

This guide has two parts:

1. **Push your existing code** to the GitHub repository you cloned.
2. **Create a branch, make a change, and open a pull request.**

All commands are run in the **VS Code terminal** (`Terminal > New Terminal`, or `` Ctrl+` ``). Make sure the terminal is open in your project folder, the one you cloned.

---

## Before You Start

- You should have created your **own empty repository** on GitHub and cloned it into VS Code. When you cloned it, you probably saw `warning: You appear to have cloned an empty repository.` That warning is expected.
- The first time you push, VS Code may open a browser window asking you to **sign in to GitHub**. Approve it.

### One-time setup: tell Git who you are

If you have never used Git on this computer, run these once (use your own name and the email on your GitHub account):

```bash
git config --global user.name "Your Name"
git config --global user.email "you@example.com"
```

---

## Part 1: Push Your Code to GitHub

### Step 1: Confirm you're in the right repository

```bash
git remote -v
```

You should see your GitHub repository URL listed next to `origin`. If you see `fatal: not a git repository`, your terminal is in the wrong folder. Use `cd` to move into your project folder, or open the correct folder in VS Code (`File > Open Folder`).

### Step 2: See what has changed

```bash
git status
```

Files listed in **red** have changes that are not yet staged.

### Step 3: Stage your changes

```bash
git add .
```

The `.` means "everything in this folder." Run `git status` again. The files should now be **green**.

### Step 4: Commit your changes

```bash
git commit -m "Add my project code"
```

A commit is a saved snapshot. The message after `-m` should briefly describe what you did.

### Step 5: Push to GitHub (first time)

Because you cloned an **empty** repository, this is the first push, so it takes two extra pieces.

First, make sure your branch is named `main`. This is harmless if it already is:

```bash
git branch -M main
```

Then push and set GitHub as the upstream for `main`:

```bash
git push -u origin main
```

After this first push, a plain `git push` is enough for future commits on `main`.

### Step 6: Verify

Open your repository on GitHub in a browser and refresh. Your files and your commit message should be there.

---

## Part 2: Create a Branch and Open a Pull Request

A **branch** lets you work on a change without touching the main code. A **pull request (PR)** asks for that change to be reviewed and merged into `main`.

### Step 1: Start from an up-to-date `main`

```bash
git checkout main
git pull
```

### Step 2: Create a new branch and switch to it

```bash
git checkout -b update-readme
```

Replace `update-readme` with a short name describing your change. Use lowercase letters and hyphens, with no spaces.

Confirm which branch you're on:

```bash
git branch
```

The branch with the `*` is your current branch. The current branch is also shown in the bottom-left corner of VS Code.

### Step 3: Make your change

Edit a file in VS Code. For example, add a line to `README.md`. **Save the file.**

### Step 4: Stage and commit

```bash
git add .
git commit -m "Update README with project description"
```

### Step 5: Push the branch to GitHub

The first time you push a new branch, you have to tell Git to create it on GitHub:

```bash
git push -u origin update-readme
```

Use your branch name in place of `update-readme`. After this first push, a plain `git push` works for that branch.

### Step 6: Open the pull request on GitHub

1. Go to your repository on GitHub.
2. You should see a yellow banner saying your branch had recent pushes. Click **Compare & pull request**.
   - If there's no banner, click the **Pull requests** tab, then **New pull request**.
3. Check the two dropdowns at the top:
   - **base:** `main` (where the change is going)
   - **compare:** your branch (where the change is coming from)
4. Add a **title** and a short **description** of what you changed and why.
5. Click **Create pull request**.

Do **not** merge the pull request unless your instructor tells you to.

---

## Doing It With the VS Code Interface (Optional)

You can also do everything above without typing commands:

| Task | Where in VS Code |
|------|------------------|
| See changes | **Source Control** icon in the left sidebar (`Ctrl+Shift+G`) |
| Stage | Click **+** next to a file, or next to "Changes" to stage everything |
| Commit | Type a message in the box at the top, then click **Commit** |
| Push | Click **Sync Changes** or **Publish Branch** |
| Create a branch | Click the branch name in the bottom-left corner, then **Create new branch** |

---

## Troubleshooting

| Error message | What it means | Fix |
|---------------|---------------|-----|
| `fatal: not a git repository` | Your terminal is not in the project folder | `cd` into the cloned folder, or open it with `File > Open Folder` |
| `Author identity unknown` / `Please tell me who you are` | Git doesn't know your name and email | Run the one-time setup commands at the top of this guide |
| `src refspec main does not match any` | Either you haven't committed yet, or your branch is named `master` | Make sure Step 4 (commit) succeeded, then run `git branch -M main` and push again |
| `nothing to commit, working tree clean` | No changes to commit | Make sure you **saved** your files |
| `rejected ... (fetch first)` or `non-fast-forward` | GitHub has commits you don't have locally | Run `git pull`, then `git push` again |
| `The current branch has no upstream branch` | New branch hasn't been pushed yet | Run `git push -u origin <your-branch-name>` |
| `403` or `Permission denied` | You're signed in to the wrong GitHub account, or this isn't your repository | Run `git remote -v` to check the URL, and sign in to VS Code with the account that owns the repository |

---

## Quick Reference

```bash
# Push existing work (first push to an empty repo)
git status
git add .
git commit -m "Describe your change"
git branch -M main
git push -u origin main

# Branch and pull request
git checkout main
git pull
git checkout -b my-branch-name
# ...edit and save files...
git add .
git commit -m "Describe your change"
git push -u origin my-branch-name
# Then open a pull request on GitHub
```
