---
name: marsai_capabilities
type: knowledge
version: 1.0.0
agent: CodeActAgent
triggers:
  - marsai
  - pipeline
  - department
  - departments
  - ceo
  - cto
  - cmo
  - coo
  - engineering
  - marketing
  - design
---

# MarsAI Company Structure & Capabilities

MarsAI is an autonomous AI technology company with 57 specialized agents across 11 departments.

## Department Overview

| Department | Head | What They Produce |
|---|---|---|
| **CTO — Engineering** | CTO Agent | Code, apps, APIs, websites, smart contracts |
| **CMO — Marketing** | CMO Agent | Marketing strategies, SEO, social media content |
| **COO — Operations** | COO Agent | UI/UX designs, project plans, visual assets |
| **CPO — Product** | CPO Agent | Product specs, user stories, roadmaps |
| **CRO — Revenue** | CRO Agent | Sales proposals, pricing, partnerships |
| **CFO — Finance** | CFO Agent | Budgets, cost analysis, financial reports |
| **CLO — Legal** | CLO Agent | Contracts, compliance, legal reviews |
| **CHRO — Agent HR** | CHRO Agent | Agent optimization, prompt engineering |
| **CDO — Data** | CDO Agent | Analytics, dashboards, data insights |
| **DPO — Data Protection** | DPO Agent | Privacy assessments, GDPR/KVKK compliance |

## CTO Engineering Teams

The CTO department has 4 specialized teams:
- **Web Team**: System Architect, Senior Full-Stack Dev, Mid-Level Dev, QA Engineer
- **Mobile Team**: Mobile Lead, iOS Dev, Android Dev, Flutter Dev
- **Blockchain Team**: Web3 Lead, Smart Contract Dev, Security Auditor, dApp Frontend Dev
- **Cloud Team**: Cloud Architect, Senior DevOps, Security Specialist

## How Tasks Flow

1. User request enters through the chat
2. CEO Agent analyzes and categorizes the task
3. CEO routes to the appropriate department
4. Department head assigns to the right team/agent
5. Work is done with quality review
6. Result returns to user

Use the `marsai_run_pipeline` tool to send tasks through this pipeline.
Use the `marsai_list_departments` tool for detailed department information.
