# Internal Developer Platforms (IDP)

## What is it

An Internal Developer Platform is the set of tools, templates, automation, and guardrails a platform team builds so that other teams can ship software safely **without having to become experts in everything underneath it**.

## Why it matters

At the university we have dozens of developers across campus. Each one needs a web app, a database, a pipeline, monitoring, backups, network rules, and an identity setup that security will sign off on. Without a platform, every team does all of that from scratch, a little differently each time.

What that looks like day to day:

- **Every request is a project.** "I need a database" turns into tickets to four teams and three weeks of waiting.
- **Every deployment is a snowflake.** Ten web apps, ten slightly different security settings. Auditors find the differences before you do.
- **Experts become bottlenecks.** The two people who understand networking get pulled into every conversation.
- **Developers carry too much in their heads.** Someone who wants to build a scheduling app now has to understand private endpoints, Key Vault, and diagnostic settings.

The goal of a platform is to **reduce cognitive load**: let people focus on the work only they can do, and make the secure, supported way also the easiest way.

## The key ideas

| Term | What it means |
|---|---|
| **Internal Developer Platform (IDP)** | The whole thing: self-service capabilities, automation, templates, and guardrails, offered by a platform team to internal teams. |
| **Internal Developer Portal** | The *front door* to the platform: a website or catalog where people find and request things (Backstage is an example example). Same acronym, different thing. A portal without a platform behind it is just a nice menu. |
| **Golden path / paved road** | The supported, opinionated way to do a common task. You *can* go off-road, but the paved road is faster, safer, and already approved. |
| **Platform as a product** | Treat internal teams as customers. Have a roadmap, talk to users, measure adoption. If nobody uses the platform, it's not done; it's failed. |
| **Thinnest viable platform** | Build the smallest platform that actually helps. Sometimes that's a wiki page and three templates, not a Kubernetes cluster. |
| **Cognitive load** | How much a person has to hold in their head to get work done. Platforms exist to reduce the load that isn't part of the team's actual job. |
| **Self-service** | Users get what they need without filing a ticket and waiting for a human. Guardrails make self-service safe. |
| **Guardrails vs. gates** | A gate stops you and makes you wait for approval. A guardrail lets you move fast but keeps you from going off the cliff (for example, Azure Policy denying a public storage account). Mature platforms favor guardrails. |

> **Watch the acronym.** In identity work, **IdP** means *Identity Provider* (like Microsoft Entra ID). Context usually makes it clear, but in a cloud class you'll hear both in the same hour.

## A little history

None of this is brand new. It's the next chapter of a story that runs through DevOps.

- **2009-2010: DevOps.** Teams started breaking down the wall between "people who write code" and "people who run it." *Continuous Delivery* (2010) made the case that releasing software should be boring and routine.
- **Mid-2010s: "You build it, you run it."** Teams got more freedom and more responsibility. It worked, but each team now had to learn infrastructure, security, monitoring, and on-call. Freedom turned into overload.
- **Netflix's "paved road."** Netflix gave engineers freedom to choose, but invested heavily in one well-supported path. Most teams chose the paved road because it was simply easier.
- **2018: Platforms get a definition.** Evan Bottcher of Thoughtworks wrote a widely cited article defining a digital platform as a foundation of self-service APIs, tools, and knowledge that lets teams deliver with reduced coordination.
- **2019: *Team Topologies*.** Matthew Skelton and Manuel Pais gave organizations a vocabulary: stream-aligned teams deliver value, and a **platform team** exists to make those teams faster.
- **2020: Spotify and golden paths.** With a fast-growing engineering org and too many ways to build the same thing, Spotify wrote about **golden paths** and open-sourced **Backstage**, its developer portal. Backstage is now a CNCF project.
- **2023-2025: Platform engineering goes mainstream.** Gartner named it a top strategic trend and predicted that by 2026, 80% of large software engineering organizations would have platform teams. The CNCF published a platforms white paper and a maturity model. DORA started measuring platforms directly.

## How it shows up in the real world

### University of Arkansas

Our cloud team is building toward a platform, guided by a **Platform Standards**:

- **Products, not one-offs.** A "product" is a tested, versioned, documented composition (say, a web app with monitoring and identity built in) that teams request through the service catalog.
- **Modules underneath.** Products are assembled from **Azure Verified Modules**, so we maintain our decisions, not boilerplate.
- **Platform separated from app code.** Developers deploy their application code. They don't deploy the infrastructure underneath it. The platform pipeline does, with scoped permissions.
- **One paved road for a hard problem.** The Fabric Private Connectivity Platform (public repo: add link once published) turns "connect a Fabric notebook to an on-prem database" from a multi-team project into a pull request to one registry file.

### Elsewhere

- **Spotify:** golden paths and Backstage.
- **Netflix:** the paved road, with freedom to leave it.
- **Microsoft:** publishes a full platform engineering guide and capability model, and builds Azure landing zones around "subscription vending" (a new, governed Azure subscription on request).

## What good looks like (and how it goes wrong)

| Good sign | Warning sign |
|---|---|
| Teams *choose* the platform because it's easier | Teams are *forced* onto the platform and route around it |
| The platform team talks to its users regularly | The platform team builds what it finds interesting |
| Starts thin and grows from real demand | Starts with a big tool purchase ("we bought a portal, so we have a platform") |
| Guardrails enforce rules automatically | Every request waits on a human approval |
| Measures adoption, lead time, and satisfaction | Measures "number of features shipped" |
| Documentation explains *why*, not just *how* | Only the people who built it can use it |

The takeaway: a platform is not automatically good. A *well-run* platform, treated as a product, is.

## Seminal works

| Work | Why it matters |
|---|---|
| Jez Humble and David Farley, ***Continuous Delivery*** (2010) | The foundation: deployment should be automated, repeatable, and boring. Platforms are how organizations make that true at scale. |
| Betsy Beyer et al. (Google), ***Site Reliability Engineering*** (2016), especially the chapter "Eliminating Toil" | Defines *toil*: manual, repetitive work that scales with growth. Platforms are a toil-elimination strategy. Free online. |
| Nicole Forsgren, Jez Humble, and Gene Kim, ***Accelerate*** (2018) | Research showing which practices actually predict software delivery performance. The source of the "DORA metrics." |
| Evan Bottcher, **"What I Talk About When I Talk About Platforms"** (martinfowler.com, 2018) | The definition of a digital platform most people still quote. Short and readable. |
| Matthew Skelton and Manuel Pais, ***Team Topologies*** (2019) | The organizational blueprint: platform teams, cognitive load, and "thinnest viable platform." If you read one book, read this one. |
| Spotify Engineering, **"How We Use Golden Paths to Solve Fragmentation in Our Software Ecosystem"** (2020) | Where "golden path" entered the mainstream vocabulary. |
| Nicole Forsgren et al., **"The SPACE of Developer Productivity"** (ACM Queue, 2021) and Abi Noda et al., **"DevEx: What Actually Drives Productivity"** (ACM Queue, 2023) | Peer-reviewed frameworks for measuring whether a platform actually helps developers. DevEx centers on feedback loops, cognitive load, and flow state. |
| CNCF TAG App Delivery, **Platforms White Paper** and **Platform Engineering Maturity Model** (2023) | Vendor-neutral, community-written definitions and a way to assess where you are. |
| Camille Fournier and Ian Nowland, ***Platform Engineering: A Guide for Technical, Product, and People Leaders*** (O'Reilly, 2024) | The most complete book on running a platform team, including the hard parts: funding, people, and migrations. |
| Gregor Hohpe, ***Platform Strategy*** (2024) | An architect's view of platforms: why they work, where they fail, and how to think about them strategically. |

## Subject-matter experts

| Who | Known for | Start with |
|---|---|---|
| **Matthew Skelton & Manuel Pais** | *Team Topologies*, platform teams, cognitive load | The book, or teamtopologies.com |
| **Nicole Forsgren** | *Accelerate*, DORA, SPACE, DevEx research | *Accelerate* |
| **Jez Humble** | *Continuous Delivery*, *Accelerate*, DORA | *Continuous Delivery* |
| **Gene Kim** | *The Phoenix Project*, *The DevOps Handbook* | *The Phoenix Project* (a novel, and a fun read) |
| **Evan Bottcher** | Defining digital platforms (Thoughtworks) | His 2018 article |
| **Camille Fournier** | *Platform Engineering*, *The Manager's Path* | *Platform Engineering* |
| **Gregor Hohpe** | *The Software Architect Elevator*, *Platform Strategy* | *The Software Architect Elevator* (great for anyone headed toward architecture) |
| **Abi Noda** | Developer experience measurement (DevEx) | The DevEx paper |
| **Kaspar von Grünberg & Luca Galante** | Building the platform engineering community (Humanitec, PlatformCon, platformengineering.org) | PlatformCon talks (free) |

## Resources

### Read
- **[Starter]** [What I Talk About When I Talk About Platforms](https://martinfowler.com/articles/talk-about-platforms.html), Evan Bottcher
- **[Starter]** [How We Use Golden Paths to Solve Fragmentation](https://engineering.atspotify.com/2020/8/how-we-use-golden-paths-to-solve-fragmentation-in-our-software-ecosystem), Spotify Engineering
- **[Starter]** [Platform engineering guide](https://learn.microsoft.com/en-us/platform-engineering/), Microsoft Learn (see "What is platform engineering?" and the capability model)
- **[Deeper]** [CNCF Platforms Working Group](https://appdelivery.cncf.io/wgs/platforms/) (white paper) and [Platform Engineering Maturity Model](https://tag-app-delivery.cncf.io/whitepapers/platform-eng-maturity-model/)
- **[Deeper]** [Eliminating Toil](https://sre.google/sre-book/eliminating-toil/), Google SRE book (free)
- **[Deeper]** [DevEx: What Actually Drives Productivity](https://queue.acm.org/detail.cfm?id=3595878), ACM Queue
- **[Deeper]** [The SPACE of Developer Productivity](https://queue.acm.org/detail.cfm?id=3454124), ACM Queue
- **[Practitioner]** [2024 DORA report](https://dora.dev/research/2024/dora-report/) (platform engineering chapter) and the [2025 State of AI-assisted Software Development](https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf)
- **[Practitioner]** [Platform Engineering](https://www.oreilly.com/library/view/platform-engineering/9781098153632/), Fournier & Nowland (O'Reilly; check the library for access)
- **[Practitioner]** [Platform Strategy](https://leanpub.com/platformstrategy), Gregor Hohpe
- **[Practitioner]** [Azure Verified Modules](https://aka.ms/avm): the building blocks for products on Azure
- **[Practitioner]** [Gartner: Platform Engineering Empowers Developers](https://gartner.com/en/experts/top-tech-trends-unpacked-series/platform-engineering-empowers-developers)

### Watch / listen
- **PlatformCon** talks (free, on YouTube). Search for talks by Manuel Pais on "platform as a product."
- [Backstage](https://backstage.io) demos, to see what a developer portal looks like.

## Talking about it in an interview

- "A platform is a product for internal customers. The test is adoption: if teams route around it, it isn't working, no matter how good the tech is."
- "I've seen how a golden path reduces cognitive load. In one example, connecting a SaaS analytics tool to an on-prem database went from a multi-team project to one reviewed pull request."
- "Guardrails beat gates. Policy that blocks a public endpoint automatically is better than an approval meeting for every deployment."
- "I'd start with the thinnest viable platform, maybe templates and documentation, and grow it from real demand rather than buying a big tool first."

## Questions to think about

1. Where is the line between a platform and a bottleneck? How would you know you'd crossed it?
2. If developers can't deploy infrastructure, what *can* they change themselves? Who decides?
3. A portal is the most visible part of a platform but often the least important. Why do organizations buy the portal first anyway?
4. How would you measure whether a platform is helping? (Hint: SPACE and DevEx.)
5. **Imagination spark:** Think about a theme park. Guests never see the tunnels, the supply lines, or the systems that make a ride run on time, but those systems are why the experience feels effortless. What would it mean to design a platform so developers have that experience?

## What we don't know yet

- **Where the infrastructure/application boundary sits** for things like app settings, scaling rules, and container image updates. We're writing a decision record on it.
- **How far to automate request-to-deployment.** The standard calls for it; today some steps are templated handoffs.
- **Portal or no portal.** Our service catalog is the front door for now. Whether we need something like Backstage is an open question, and "not yet" is a fine answer.
- **How AI changes this.** The 2025 DORA findings suggest platforms are what make AI-assisted development safe at scale. What that looks like for us is still emerging.

