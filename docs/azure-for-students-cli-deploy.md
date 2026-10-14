# Azure for Students: Deploying with the CLI

This guide takes the Terraform code you wrote in **Terraform on Azure: Building a Web App with Dev and Prod Environments** and deploys it to your own Azure subscription. You'll deploy to **dev** first, put a small web application on it, confirm it works, and then promote it to **prod**.

All commands run in the **VS Code terminal**, from your project folder. Commands are shown for both **macOS/Linux (bash/zsh)** and **Windows (PowerShell)** where they differ.

> **Using OpenTofu?** Type `tofu` everywhere this guide says `terraform`.

---

## Part 1: Install the Tools

You need two command-line tools: the **Azure CLI** (`az`) and **Terraform**.

### Windows (PowerShell)

```powershell
winget install --exact --id Microsoft.AzureCLI
winget install --exact --id Hashicorp.Terraform
```

### macOS (Homebrew)

```bash
brew install azure-cli
brew tap hashicorp/tap
brew install hashicorp/tap/terraform
```

### Verify

**Close and reopen VS Code** so the terminal picks up the new tools, then run:

```bash
az version
terraform version
```

Both should print a version number. If you see `command not found` or `is not recognized`, VS Code hasn't picked up the install yet. Restart VS Code fully, not just the terminal.

---

## Part 2: Activate Azure for Students

Azure for Students gives full-time university students **$100 in Azure credit for 12 months**. **No credit card is required.**

1. Go to **https://azure.microsoft.com/free/students**.
2. Click **Start free**.
3. Sign in with your **university email address**.
4. Complete the student verification and accept the terms.
5. Wait for the confirmation that your subscription is ready. This can take a few minutes.

### Watch your credit

You can check how much credit you have left on the **Azure Sponsorships portal** (https://www.microsoftazuresponsorships.com). Get in the habit of checking it. When the credit runs out, your subscription is disabled.

---

## Part 3: Sign In from the Terminal

### Step 1: Sign in

```bash
az login
```

A browser window (or a Windows account picker) opens. Sign in with your **university account**.

If the browser doesn't open, use the device-code flow instead and follow the instructions it prints:

```bash
az login --use-device-code
```

### Step 2: Select your Azure for Students subscription

List the subscriptions your account can see:

```bash
az account list --output table
```

Set the Azure for Students subscription as active:

```bash
az account set --subscription "Azure for Students"
```

Confirm it worked:

```bash
az account show --output table
```

The `Name` column should say **Azure for Students**.

### Step 3: Tell Terraform which subscription to use

Your Terraform code intentionally has no subscription ID in it. Provide it through an environment variable instead.

**macOS/Linux:**

```bash
export ARM_SUBSCRIPTION_ID=$(az account show --query id --output tsv)
```

**Windows PowerShell:**

```powershell
$env:ARM_SUBSCRIPTION_ID = az account show --query id --output tsv
```

> **This only lasts for the current terminal.** If you close the terminal or restart VS Code, run this command again before using Terraform.

---

## Part 4: Find Your Allowed Regions

**Do not skip this.** Azure for Students subscriptions can only deploy resources to a short list of regions, and **the list is different for different students**. If you deploy to a region that isn't on your list, the deployment fails with `RequestDisallowedByAzure`.

1. Sign in to the **Azure portal** (https://portal.azure.com).
2. Search for **Policy** and open it.
3. Under **Authoring**, select **Assignments**.
4. Open the assignment named **Allowed resource deployment regions** (or similar, such as **Allowed locations**).
5. Look at the **Allowed locations** parameter. These are the regions you can use.

Pick one region from your list. Open **both** `environments/dev.tfvars` and `environments/prod.tfvars`, and replace the `location` value with it. Use the short name with no spaces, such as `eastus2` or `westus3`, not the display name `East US 2`.

```hcl
location = "eastus2" # use a region from YOUR allowed list
```

Commit this change:

```bash
git add environments/
git commit -m "Set Azure region to an allowed region"
git push
```

---

## Part 5: Deploy to Dev

### Step 1: Initialize (if you haven't already)

```bash
terraform init
```

### Step 2: Create and select the dev workspace

```bash
terraform workspace select -or-create dev
```

Confirm which workspace you're in:

```bash
terraform workspace show
```

It should print `dev`. **Check this every time before you plan or apply.**

### Step 3: Preview the changes

```bash
terraform plan -var-file="environments/dev.tfvars" -out="dev.tfplan"
```

Read the output. The last line should say something like:

```text
Plan: 7 to add, 0 to change, 0 to destroy.
```

Scroll up and look at what Terraform intends to create. Every resource name should end in `-dev` or contain `dev`. If you see `prod` anywhere, stop. You used the wrong `.tfvars` file.

`-out="dev.tfplan"` saves this exact plan. In the next step, Terraform applies **exactly** what you reviewed, nothing more.

### Step 4: Apply

```bash
terraform apply "dev.tfplan"
```

This takes several minutes. **The first apply in a new subscription is the slowest**, because Azure has to enable (register) the services Terraform uses.

When it finishes, you'll see:

```text
Apply complete! Resources: 7 added, 0 changed, 0 destroyed.
```

followed by your outputs, including `web_app_url`.

### Step 5: Look at what you built

See your outputs again at any time:

```bash
terraform output
```

List the resources in your dev resource group:

```bash
az resource list --resource-group rg-webapp-dev --output table
```

Open the `web_app_url` in a browser. You should see Azure's default placeholder page. Your infrastructure is running, but it has no application code yet.

---

## Part 6: Deploy Application Code to Dev

Infrastructure alone isn't a full deploy. Now you'll put a small Node.js application on the web app.

### Step 1: Create the application files

In your project, create a folder named `app` with these two files.

**`app/package.json`**

```json
{
  "name": "webapp",
  "version": "1.0.0",
  "private": true,
  "scripts": {
    "start": "node server.js"
  },
  "engines": {
    "node": ">=20"
  }
}
```

**`app/server.js`**

```javascript
const http = require("http");

// App Service tells the app which port to listen on through PORT.
const port = process.env.PORT || 8080;
const environment = process.env.ENVIRONMENT || "local";

const server = http.createServer((req, res) => {
  res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
  res.end(`<!doctype html>
<html>
  <head><title>Web App (${environment})</title></head>
  <body style="font-family: sans-serif; margin: 3rem;">
    <h1>Hello from Azure App Service</h1>
    <p>Environment: <strong>${environment}</strong></p>
    <p>Deployed with Terraform and the Azure CLI.</p>
  </body>
</html>`);
});

server.listen(port, () => {
  console.log(`Listening on port ${port} (${environment})`);
});
```

The app displays the value of the `ENVIRONMENT` setting, which your Terraform code set on the web app. That's how you'll be able to tell dev and prod apart in the browser.

### Step 2: Package the app as a zip file

The two files must be at the **top level** of the zip, not inside an `app` folder within the zip.

**macOS/Linux:**

```bash
cd app && zip -r ../app.zip . && cd ..
```

**Windows PowerShell:**

```powershell
Compress-Archive -Path app\* -DestinationPath app.zip -Force
```

### Step 3: Deploy the zip to the dev web app

Make sure you're still in the `dev` workspace (`terraform workspace show`), then run:

```bash
az webapp deploy --resource-group "$(terraform output -raw resource_group_name)" --name "$(terraform output -raw web_app_name)" --src-path app.zip --type zip
```

This command reads the resource group and web app names straight from your Terraform outputs, so you don't have to copy the random suffix by hand. It works the same in bash and PowerShell.

### Step 4: Verify

Open your `web_app_url` again. You should see:

> **Hello from Azure App Service**
> Environment: **dev**

The first request after a deploy can take 30 seconds or more while the app starts. If you see an error page, wait a minute and refresh before troubleshooting.

**This is the point of dev.** If something is broken, you found it here, and prod was never affected.

---

## Part 7: Promote to Prod

Once dev works, deploy the **same code** to prod.

### Step 1: Switch to the prod workspace

```bash
terraform workspace select -or-create prod
terraform workspace show
```

It should print `prod`.

### Step 2: Plan and apply with the prod variables

```bash
terraform plan -var-file="environments/prod.tfvars" -out="prod.tfplan"
```

Every resource name should now contain `prod`. Then:

```bash
terraform apply "prod.tfplan"
```

> **Prod costs money.** Prod uses the `B1` App Service plan, which is billed against your credit for every hour it exists. Destroy prod when you're finished with the assignment (Part 9).

### Step 3: Deploy the app to prod

```bash
az webapp deploy --resource-group "$(terraform output -raw resource_group_name)" --name "$(terraform output -raw web_app_name)" --src-path app.zip --type zip
```

Because you're in the `prod` workspace, `terraform output` now returns the **prod** names. Open the prod `web_app_url` and confirm it says **Environment: prod**.

You now have two separate environments built from one set of code.

---

## Part 8: Push Your Work to GitHub

```bash
git status
```

Check the list before you stage anything:

- **Should appear:** `app/package.json`, `app/server.js`, your `.tf` files, your `.tfvars` files, `.terraform.lock.hcl`
- **Must not appear:** anything ending in `.tfstate`, `.tfplan`, the `terraform.tfstate.d/` folder, the `.terraform/` folder, or `app.zip`

If any of the "must not appear" files show up, your `.gitignore` is missing or incomplete. Fix it before continuing.

```bash
git add .
git commit -m "Add sample app and deploy dev and prod"
git push
```

> **Your state lives only on your computer.** The `terraform.tfstate.d/` folder is how Terraform knows what it built. If you delete it or switch computers, Terraform loses track of your resources. In real teams, state is stored remotely (for example, in an Azure storage account) so it's shared and backed up.

---

## Part 9: Tear Down

When you're finished, delete both environments so they stop using your credit.

### Destroy prod

```bash
terraform workspace select prod
terraform destroy -var-file="environments/prod.tfvars"
```

Terraform lists everything it will delete and asks you to type `yes`.

### Destroy dev

```bash
terraform workspace select dev
terraform destroy -var-file="environments/dev.tfvars"
```

### If Terraform lost track (fallback)

If your state was deleted or you're on a different computer, delete the resource groups directly. This removes everything inside them:

```bash
az group delete --name rg-webapp-dev --yes
az group delete --name rg-webapp-prod --yes
```

### Confirm nothing is left

```bash
az group list --output table
```

`rg-webapp-dev` and `rg-webapp-prod` should no longer be listed. (Azure sometimes creates its own helper resource groups, such as `NetworkWatcherRG` or `DefaultResourceGroup-…`. Those are fine to leave.)

---

## Troubleshooting

Find the error message you're seeing in the left column.

| Error message contains | What it means | Fix |
|------------------------|---------------|-----|
| `RequestDisallowedByAzure` | The region isn't on your subscription's allowed list | Repeat Part 4 and use a region from **your** list, in both `.tfvars` files |
| `Operation cannot be completed without additional quota` | Your subscription has no App Service capacity for this plan size in this region | Try a different region from your allowed list. Note whether the error was for `F1` (dev) or `B1` (prod); quota is separate for each. |
| `subscription_id` | Terraform doesn't know which subscription to use | Run the `ARM_SUBSCRIPTION_ID` command from Part 3, Step 3 (you probably opened a new terminal) |
| `Workspace and environment do not match` | You're in one workspace but passed the other environment's `.tfvars` file | Run `terraform workspace show`, then use the matching `.tfvars` file |
| `MissingSubscriptionRegistration` | An Azure service isn't enabled in your subscription yet | Run `az provider register --namespace <the namespace in the error>`, wait a few minutes, then plan and apply again |
| `Saved plan is stale` | Something changed after you ran `plan` | Run `plan` again with `-out`, then apply the new plan file |
| `No subscriptions found` or `AADSTS` errors at login | You signed in with the wrong account | Run `az logout`, then `az login` with your **university** account |
| Web page shows `Application Error` | The app failed to start | Wait a minute and refresh. If it persists, check that `package.json` and `server.js` are at the top level of the zip, then rebuild the zip and deploy again. |

---

## Command Summary

```bash
# Sign in (once per session)
az login
az account set --subscription "Azure for Students"
export ARM_SUBSCRIPTION_ID=$(az account show --query id --output tsv)   # PowerShell: $env:ARM_SUBSCRIPTION_ID = az account show --query id --output tsv

# Deploy dev
terraform init
terraform workspace select -or-create dev
terraform plan -var-file="environments/dev.tfvars" -out="dev.tfplan"
terraform apply "dev.tfplan"
az webapp deploy --resource-group "$(terraform output -raw resource_group_name)" --name "$(terraform output -raw web_app_name)" --src-path app.zip --type zip

# Promote to prod
terraform workspace select -or-create prod
terraform plan -var-file="environments/prod.tfvars" -out="prod.tfplan"
terraform apply "prod.tfplan"
az webapp deploy --resource-group "$(terraform output -raw resource_group_name)" --name "$(terraform output -raw web_app_name)" --src-path app.zip --type zip

# Tear down
terraform workspace select prod
terraform destroy -var-file="environments/prod.tfvars"
terraform workspace select dev
terraform destroy -var-file="environments/dev.tfvars"
```
