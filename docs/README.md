# SimBoard Documentation

Documentation for the SimBoard project.

---

## 📁 Documentation Structure

```bash
docs/
├── README.md           # This file
├── cicd/               # CI/CD and deployment
│   ├── README.md       # Quick start and overview
│   └── DEPLOYMENT.md   # Complete reference guide
└── deploy/             # Environment-specific deployment runbooks
    └── spin.md         # Spin backend migration rollout + frontend/db/ingress config
```

---

## 🚀 CI/CD Quick Links

**New to CI/CD setup?**

- [cicd/README.md](cicd/README.md) - Quick start guide

**Need deployment details?**

- [cicd/DEPLOYMENT.md](cicd/DEPLOYMENT.md) - Complete reference
- [deploy/spin.md](deploy/spin.md) - Spin backend/frontend/db/ingress workload runbook

---

## 📚 CI/CD Documentation

All CI/CD and deployment documentation is in the [`cicd/`](cicd/) directory:

- **[cicd/README.md](cicd/README.md)** - Quick start, overview, and common operations
- **[cicd/DEPLOYMENT.md](cicd/DEPLOYMENT.md)** - Complete deployment guide with workflows, Kubernetes examples, and troubleshooting
- **[deploy/spin.md](deploy/spin.md)** - Spin-specific backend migration-first plus frontend/db/ingress runbook

---

## 🔗 External Links

- [NERSC Registry](https://registry.nersc.gov/harbor/projects)
- [NERSC Spin Dashboard](https://rancher2.spin.nersc.gov/)
- [GitHub Actions](https://github.com/E3SM-Project/simboard/actions)
