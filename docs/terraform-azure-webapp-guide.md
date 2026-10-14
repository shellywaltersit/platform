# Terraform on Azure: Building a Web App with Dev and Prod Environments

In this guide you will write Terraform code in VS Code that builds a complete web application environment in Azure. You'll build it twice from the same code: once as **dev** and once as **prod**.

When you finish this guide, your code will be written and checked locally. The companion guide, **Azure for Students: Deploying with the CLI**, walks you through signing in to Azure and actually deploying it.

---

## Part 1: What Is Terraform?

**Terraform is a tool that builds cloud infrastructure from code.** Instead of clicking through the Azure portal, you describe what you want in text files. Terraform then figures out how to make Azure match that description.

This approach is called **Infrastructure as Code (IaC)**. It gives you:

- **Repeatability.** The same code builds the same environment every time. That's how dev and prod can be identical in structure.
- **Version control.** Your infrastructure lives in Git, so changes are reviewed in pull requests just like application code.
- **A preview before changes.** Terraform shows you exactly what it will create, change, or delete before it touches anything.
- **Clean teardown.** One command removes everything Terraform built.

### Declarative, not step-by-step

Terraform is **declarative**. You describe the end state ("there should be a web app named X"), not the steps to get there. If the web app already exists and matches, Terraform does nothing. If it's missing, Terraform creates it. If you change a setting, Terraform updates only that setting.

### Key concepts

| Term | What it means |
|------|---------------|
| **Provider** | A plugin that knows how to talk to one platform. We use `azurerm` (Azure) and `random`. |
| **Resource** | One piece of infrastructure, such as a resource group or a web app. |
| **Variable** | An input value, so the same code can produce different environments. |
| **Output** | A value Terraform prints after it runs, such as your web app's URL. |
| **State** | Terraform's record of what it has built. It compares state to your code to decide what to change. |
| **Workspace** | A separate copy of state. We use one workspace for dev and one for prod. |

### The workflow

Every Terraform project follows the same loop:

| Command | What it does | Needs Azure sign-in? |
|---------|--------------|----------------------|
| `terraform init` | Downloads providers and prepares the folder | No |
| `terraform fmt` | Formats your code consistently | No |
| `terraform validate` | Checks your code for errors | No |
| `terraform plan` | Previews what will change in Azure | **Yes** |
| `terraform apply` | Makes the changes | **Yes** |
| `terraform destroy` | Deletes everything Terraform built | **Yes** |

> **Terraform or OpenTofu?** OpenTofu is an open-source fork of Terraform. The code in this guide works with both. If you use OpenTofu, type `tofu` everywhere this guide says `terraform`.

---

## Part 2: What We're Building

| Abbreviation | Resource | Purpose |
|--------------|----------|---------|
| **rg** | Resource group | A container that holds everything else. Deleting it deletes all its contents. |
| **law** | Log Analytics workspace | Central storage for logs and monitoring data |
| **appi** | Application Insights | Monitors your web app: requests, errors, response times. Sends its data to the Log Analytics workspace. |
| **asp** | App Service plan | The compute (the "server") your web app runs on. Its size determines cost. |
| **app** | Web app | Your actual website, running on the App Service plan |
| **st** | Storage account | File and blob storage for the application |
| **sql** + **sqldb** | Azure SQL server and database | *Optional.* A relational database (SQL Server). |
| **psql** + **psqldb** | PostgreSQL flexible server and database | *Optional.* A relational database (PostgreSQL). |

The names follow a pattern: `<abbreviation>-<project>-<environment>`. In dev, your resource group is `rg-webapp-dev`. In prod, it's `rg-webapp-prod`.

Some Azure names must be **globally unique**: the web app, storage account, and database servers. No two people anywhere in Azure can use the same name. To prevent collisions with your classmates, Terraform adds a random 5-character suffix to those names, for example `app-webapp-dev-k3x9p`.

---

## Part 3: Why Dev and Prod?

Professional teams never change production first. They deploy to a **dev** environment, confirm it works, and then **promote** the same code to **prod**.

Testing on your laptop is not the same as testing in dev. Dev is a real Azure deployment, with real networking, real permissions, and real regional limits. Problems you'd never see locally show up there, before they can break prod.

### How we separate them

We use the **same code** for both environments. Two things keep them apart:

1. **Workspaces separate the state.** Terraform keeps one state for the `dev` workspace and another for `prod`. Applying in dev can never modify prod.
2. **`.tfvars` files hold the differences.** `environments/dev.tfvars` and `environments/prod.tfvars` set the values that differ between environments, such as the App Service plan size.

| Setting | Dev | Prod | Why |
|---------|-----|------|-----|
| App Service plan | `F1` (free) | `B1` (paid, small) | Prod gets Always On and dedicated compute |
| Everything else | Same | Same | Dev should mirror prod as closely as possible |

The code also includes a **safety check**. If your workspace and your `.tfvars` file don't match (for example, you're in the `prod` workspace but passed `dev.tfvars`), the plan stops with an error before anything is built.

---

## Part 4: Set Up VS Code

### Install the extension

1. Open the **Extensions** panel (`Ctrl+Shift+X`, or `Cmd+Shift+X` on Mac).
2. Search for **HashiCorp Terraform** and install the one published by **HashiCorp** (`hashicorp.terraform`).

The extension gives you syntax highlighting, autocomplete for resource names and arguments, hover documentation, and error highlighting as you type. It works for both Terraform and OpenTofu.

### Turn on format-on-save (recommended)

Create a folder named `.vscode` in your project, and inside it a file named `settings.json`:

```json
{
  "[terraform]": {
    "editor.defaultFormatter": "hashicorp.terraform",
    "editor.formatOnSave": true
  },
  "[terraform-vars]": {
    "editor.defaultFormatter": "hashicorp.terraform",
    "editor.formatOnSave": true
  }
}
```

Every time you save a `.tf` file, VS Code will line up the `=` signs and fix indentation automatically.

---

## Part 5: Project Structure

Create this folder layout in your repository:

```text
your-repo/
├── .gitignore
├── .vscode/
│   └── settings.json
├── providers.tf
├── variables.tf
├── main.tf
├── outputs.tf
└── environments/
    ├── dev.tfvars
    └── prod.tfvars
```

Terraform reads **every `.tf` file in the folder** and treats them as one configuration. The split into separate files is for humans; it keeps the code organized.

### Create the `.gitignore` first

**Do this before you run `terraform init`.** Terraform creates files that must never be committed. State files can contain passwords and connection strings in plain text.

```gitignore
# Terraform working folder (providers are re-downloaded by `terraform init`)
.terraform/

# State files: contain passwords and connection strings in plain text
*.tfstate
*.tfstate.*
terraform.tfstate.d/

# Saved plans: also contain sensitive values
*.tfplan

# Crash logs
crash.log
crash.*.log

# Packaged application code (rebuilt before each deploy)
app.zip
```

> **Do commit** `.terraform.lock.hcl`. It records the exact provider versions you used, so everyone gets the same versions.

---

## Part 6: Write the Code

Create each file below. Read the comments; they explain what each block does.

### `providers.tf`: which plugins Terraform needs

```hcl
terraform {
  required_version = ">= 1.6"

  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "~> 4.0"
    }
    random = {
      source  = "hashicorp/random"
      version = "~> 3.6"
    }
  }
}

# The subscription ID is NOT written here. Terraform reads it from the
# ARM_SUBSCRIPTION_ID environment variable, so no IDs end up in Git.
provider "azurerm" {
  features {}
}
```

**What's happening here:**

- `required_providers` tells Terraform to download the Azure (`azurerm`) and `random` providers.
- `version = "~> 4.0"` means "any 4.x version, but not 5.0." This protects you from breaking changes in a future major version.
- The `features {}` block is required by the Azure provider, even when empty.
- Notice there's **no subscription ID** in the code. You'll provide it with an environment variable when you deploy, so it never ends up in Git.

### `variables.tf`: the inputs

```hcl
variable "project" {
  description = "Short project name used in every resource name. Lowercase letters and numbers only."
  type        = string
  default     = "webapp"

  validation {
    condition     = can(regex("^[a-z0-9]{3,10}$", var.project))
    error_message = "project must be 3-10 lowercase letters or numbers (it becomes part of the storage account name)."
  }
}

variable "environment" {
  description = "Environment name. Must match the current workspace (dev or prod)."
  type        = string

  validation {
    condition     = contains(["dev", "prod"], var.environment)
    error_message = "environment must be \"dev\" or \"prod\"."
  }
}

variable "location" {
  description = "Azure region. Must be one your subscription is allowed to use."
  type        = string
}

variable "app_service_sku" {
  description = "App Service plan size. F1 is free; B1 is the smallest paid tier."
  type        = string
  default     = "F1"
}

variable "log_retention_days" {
  description = "How long Log Analytics keeps data."
  type        = number
  default     = 30
}

variable "enable_sql" {
  description = "Create an Azure SQL server and database."
  type        = bool
  default     = false
}

variable "enable_postgres" {
  description = "Create an Azure Database for PostgreSQL flexible server."
  type        = bool
  default     = false
}
```

**What's happening here:**

- Each `variable` block declares an input with a type, a description, and sometimes a default.
- `environment` and `location` have **no default**, so they must come from a `.tfvars` file.
- The `validation` blocks reject bad values before Terraform talks to Azure. Try setting `environment = "test"` later and run `terraform validate` to see one in action.

### `main.tf`: the resources

```hcl
# ---------------------------------------------------------------------------
# Naming
# ---------------------------------------------------------------------------

# A random suffix keeps globally unique names (web app, storage, databases)
# from colliding with other students. Each workspace has its own state, so
# dev and prod get different suffixes.
resource "random_string" "suffix" {
  length  = 5
  upper   = false
  special = false
}

locals {
  name   = "${var.project}-${var.environment}"
  suffix = random_string.suffix.result

  tags = {
    project     = var.project
    environment = var.environment
    managed_by  = "terraform"
  }
}

# ---------------------------------------------------------------------------
# Resource group (rg)
# ---------------------------------------------------------------------------

resource "azurerm_resource_group" "rg" {
  name     = "rg-${local.name}"
  location = var.location
  tags     = local.tags

  lifecycle {
    precondition {
      condition     = terraform.workspace == var.environment
      error_message = "Workspace and environment do not match. Run 'terraform workspace select ${var.environment}' or use the matching .tfvars file."
    }
  }
}

# ---------------------------------------------------------------------------
# Monitoring: Log Analytics workspace (law) + Application Insights (appi)
# ---------------------------------------------------------------------------

resource "azurerm_log_analytics_workspace" "law" {
  name                = "law-${local.name}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  sku                 = "PerGB2018"
  retention_in_days   = var.log_retention_days
  tags                = local.tags
}

resource "azurerm_application_insights" "appi" {
  name                = "appi-${local.name}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  workspace_id        = azurerm_log_analytics_workspace.law.id
  application_type    = "web"
  tags                = local.tags
}

# ---------------------------------------------------------------------------
# App Service plan (asp) + web app
# ---------------------------------------------------------------------------

resource "azurerm_service_plan" "asp" {
  name                = "asp-${local.name}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  os_type             = "Linux"
  sku_name            = var.app_service_sku
  tags                = local.tags
}

resource "azurerm_linux_web_app" "app" {
  name                = "app-${local.name}-${local.suffix}"
  location            = azurerm_resource_group.rg.location
  resource_group_name = azurerm_resource_group.rg.name
  service_plan_id     = azurerm_service_plan.asp.id
  https_only          = true
  tags                = local.tags

  site_config {
    # The free tier (F1) does not support Always On.
    always_on = var.app_service_sku != "F1"

    application_stack {
      node_version = "22-lts"
    }
  }

  app_settings = {
    APPLICATIONINSIGHTS_CONNECTION_STRING = azurerm_application_insights.appi.connection_string
    ENVIRONMENT                           = var.environment
  }

  # Only added when the matching database is enabled.
  dynamic "connection_string" {
    for_each = var.enable_sql ? [1] : []
    content {
      name  = "SqlDb"
      type  = "SQLAzure"
      value = "Server=tcp:${azurerm_mssql_server.sql[0].fully_qualified_domain_name},1433;Database=${azurerm_mssql_database.sqldb[0].name};User ID=${azurerm_mssql_server.sql[0].administrator_login};Password=${random_password.sql[0].result};Encrypt=true;"
    }
  }

  dynamic "connection_string" {
    for_each = var.enable_postgres ? [1] : []
    content {
      name  = "PostgresDb"
      type  = "PostgreSQL"
      value = "Host=${azurerm_postgresql_flexible_server.psql[0].fqdn};Database=${azurerm_postgresql_flexible_server_database.psqldb[0].name};Username=${azurerm_postgresql_flexible_server.psql[0].administrator_login};Password=${random_password.psql[0].result};SslMode=Require"
    }
  }
}

# ---------------------------------------------------------------------------
# Storage account (st)
# ---------------------------------------------------------------------------

# Storage account names: 3-24 characters, lowercase letters and numbers only,
# globally unique. No hyphens allowed.
resource "azurerm_storage_account" "st" {
  name                            = "st${var.project}${var.environment}${local.suffix}"
  location                        = azurerm_resource_group.rg.location
  resource_group_name             = azurerm_resource_group.rg.name
  account_tier                    = "Standard"
  account_replication_type        = "LRS"
  min_tls_version                 = "TLS1_2"
  allow_nested_items_to_be_public = false
  tags                            = local.tags
}

# ---------------------------------------------------------------------------
# OPTIONAL: Azure SQL (sql + sqldb). Turn on with enable_sql = true.
# ---------------------------------------------------------------------------

resource "random_password" "sql" {
  count   = var.enable_sql ? 1 : 0
  length  = 24
  special = true
}

resource "azurerm_mssql_server" "sql" {
  count                        = var.enable_sql ? 1 : 0
  name                         = "sql-${local.name}-${local.suffix}"
  location                     = azurerm_resource_group.rg.location
  resource_group_name          = azurerm_resource_group.rg.name
  version                      = "12.0"
  administrator_login          = "sqladmin${var.environment}"
  administrator_login_password = random_password.sql[0].result
  minimum_tls_version          = "1.2"
  tags                         = local.tags
}

resource "azurerm_mssql_database" "sqldb" {
  count       = var.enable_sql ? 1 : 0
  name        = "sqldb-${local.name}"
  server_id   = azurerm_mssql_server.sql[0].id
  sku_name    = "Basic"
  max_size_gb = 2
  tags        = local.tags
}

# 0.0.0.0 to 0.0.0.0 is Azure's special rule meaning "allow Azure services",
# which lets the web app reach the database.
resource "azurerm_mssql_firewall_rule" "allow_azure" {
  count            = var.enable_sql ? 1 : 0
  name             = "AllowAzureServices"
  server_id        = azurerm_mssql_server.sql[0].id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}

# ---------------------------------------------------------------------------
# OPTIONAL: PostgreSQL flexible server (psql + psqldb). enable_postgres = true.
# ---------------------------------------------------------------------------

resource "random_password" "psql" {
  count   = var.enable_postgres ? 1 : 0
  length  = 24
  special = false
}

resource "azurerm_postgresql_flexible_server" "psql" {
  count                         = var.enable_postgres ? 1 : 0
  name                          = "psql-${local.name}-${local.suffix}"
  location                      = azurerm_resource_group.rg.location
  resource_group_name           = azurerm_resource_group.rg.name
  version                       = "16"
  sku_name                      = "B_Standard_B1ms"
  storage_mb                    = 32768
  administrator_login           = "psqladmin"
  administrator_password        = random_password.psql[0].result
  public_network_access_enabled = true
  tags                          = local.tags

  # Azure picks an availability zone if we don't. Ignoring it stops
  # Terraform from trying to "fix" the zone on every plan.
  lifecycle {
    ignore_changes = [zone]
  }
}

resource "azurerm_postgresql_flexible_server_database" "psqldb" {
  count     = var.enable_postgres ? 1 : 0
  name      = "appdb"
  server_id = azurerm_postgresql_flexible_server.psql[0].id
  charset   = "UTF8"
  collation = "en_US.utf8"
}

resource "azurerm_postgresql_flexible_server_firewall_rule" "allow_azure" {
  count            = var.enable_postgres ? 1 : 0
  name             = "AllowAzureServices"
  server_id        = azurerm_postgresql_flexible_server.psql[0].id
  start_ip_address = "0.0.0.0"
  end_ip_address   = "0.0.0.0"
}
```

**What's happening here:**

- **References connect resources.** `azurerm_resource_group.rg.name` means "the `name` of the resource group I called `rg`." Terraform uses these references to work out the build order: the resource group first, then everything inside it.
- **`locals`** are calculated values used throughout the file, such as the name pattern and the tags.
- **The `precondition`** on the resource group is the dev/prod safety check described in Part 3.
- **`count`** creates a resource 0 or 1 times. `count = var.enable_sql ? 1 : 0` means "create one if `enable_sql` is true, otherwise none." That's why the SQL resources are referenced with `[0]`.
- **`dynamic "connection_string"`** adds a database connection string to the web app only when that database exists.
- **`random_password`** generates the database passwords, so nobody has to type or share one. The passwords are stored in Terraform state, which is one more reason state never goes in Git.

### `outputs.tf`: what Terraform reports back

```hcl
output "resource_group_name" {
  value = azurerm_resource_group.rg.name
}

output "web_app_name" {
  value = azurerm_linux_web_app.app.name
}

output "web_app_url" {
  value = "https://${azurerm_linux_web_app.app.default_hostname}"
}

output "storage_account_name" {
  value = azurerm_storage_account.st.name
}

output "sql_server_fqdn" {
  value = var.enable_sql ? azurerm_mssql_server.sql[0].fully_qualified_domain_name : null
}

output "postgres_server_fqdn" {
  value = var.enable_postgres ? azurerm_postgresql_flexible_server.psql[0].fqdn : null
}
```

After `terraform apply`, these values print in the terminal. You can see them again any time with `terraform output`.

### `environments/dev.tfvars`

```hcl
environment        = "dev"
location           = "centralus" # replace with a region your subscription allows
app_service_sku    = "F1"
log_retention_days = 30
enable_sql         = false
enable_postgres    = false
```

### `environments/prod.tfvars`

```hcl
environment        = "prod"
location           = "centralus" # replace with a region your subscription allows
app_service_sku    = "B1"
log_retention_days = 30
enable_sql         = false
enable_postgres    = false
```

> **About `location`:** Azure for Students subscriptions can only deploy to a short list of regions, and that list varies by subscription. The deployment guide shows you how to find yours. Until then, leave `centralus` as a placeholder.

---

## Part 7: Optional Databases

Both databases are **off by default**. To turn one on, set it to `true` in a `.tfvars` file:

```hcl
enable_sql = true
```

or

```hcl
enable_postgres = true
```

Before you enable one, know what it costs:

| Database | Tier in this code | Notes |
|----------|-------------------|-------|
| Azure SQL | `Basic`, 2 GB | Small monthly cost, charged against your credit while it exists |
| PostgreSQL flexible server | `B_Standard_B1ms`, 32 GB | Burstable tier. Not available in every region, so check your allowed regions. |

A good habit: enable a database in **dev only** first. Confirm the app can reach it, then enable it in prod.

Turning a database back to `false` and applying again **deletes it and its data**. Terraform will show this in the plan as `destroy`. Always read the plan.

---

## Part 8: Check Your Work Locally

None of these commands need an Azure sign-in. Run them in the VS Code terminal from your project folder.

### 1. Format your code

```bash
terraform fmt
```

It prints the names of any files it reformatted. If it prints nothing, your formatting was already correct.

### 2. Initialize the folder

```bash
terraform init
```

Look for `Terraform has been successfully initialized!` This creates the `.terraform` folder and the `.terraform.lock.hcl` file.

### 3. Validate your code

```bash
terraform validate
```

Look for `Success! The configuration is valid.`

If you see an error, read it carefully. Terraform tells you the **file**, the **line number**, and what's wrong. Common causes:

| Error message contains | Likely cause |
|------------------------|--------------|
| `Unsupported argument` | An argument name is misspelled or doesn't belong in that block |
| `Missing required argument` | A block is missing a setting it needs |
| `Reference to undeclared resource` | A typo in a reference, such as `azurerm_resource_group.rq` instead of `.rg` |
| `Unclosed configuration block` | A missing `}` |

### 4. Commit and push

Before committing, run `git status` and confirm that **no** `.tfstate`, `.tfplan`, or `.terraform/` files appear. Your two `.tfvars` files **should** appear; they contain no secrets and are part of your configuration. Then:

```bash
git add .
git commit -m "Add Terraform configuration for web app"
git push
```

---

## What's Next

Your code is written and validated. Continue with **Azure for Students: Deploying with the CLI** to:

1. Activate your Azure for Students subscription
2. Sign in from the terminal
3. Deploy to **dev**, deploy application code, and verify it works
4. Promote to **prod**
5. Tear everything down when you're done
