# Fishi

> **Fishi** is a fork of [MiroFish](https://github.com/rithythul/mirofish) with self-hosted **Neo4j** graph database for enhanced privacy and control. 
> 
> **Planned Integrations:** Facebook, Instagram, TikTok, and other social media platforms for comprehensive social simulation.

---

## ⚡ Overview

**Fishi** is a next-generation AI prediction engine powered by multi-agent technology. By extracting seed information from the real world (such as breaking news, policy drafts, or financial signals), it automatically constructs a high-fidelity parallel digital world. Within this space, thousands of intelligent agents with independent personalities, long-term memory, and behavioral logic freely interact and undergo social evolution. You can inject variables dynamically from a "God's-eye view" to precisely deduce future trajectories — **rehearse the future in a digital sandbox, and win decisions after countless simulations**.

> You only need to: Upload seed materials (data analysis reports or interesting novel stories) and describe your prediction requirements in natural language</br>
> Fishi will return: A detailed prediction report and a deeply interactive high-fidelity digital world

### Our Vision

Fishi is dedicated to creating a swarm intelligence mirror that maps reality. By capturing the collective emergence triggered by individual interactions, we break through the limitations of traditional prediction:

- **At the Macro Level**: We are a rehearsal laboratory for decision-makers, allowing policies and public relations to be tested at zero risk
- **At the Micro Level**: We are a creative sandbox for individual users — whether deducing novel endings or exploring imaginative scenarios, everything can be fun, playful, and accessible

From serious predictions to playful simulations, we let every "what if" see its outcome, making it possible to predict anything.

## 🔄 Workflow

1. **Graph Building**: Seed extraction & Individual/collective memory injection & GraphRAG construction
2. **Environment Setup**: Entity relationship extraction & Persona generation & Agent configuration injection
3. **Simulation**: Dual-platform parallel simulation & Auto-parse prediction requirements & Dynamic temporal memory updates
4. **Report Generation**: ReportAgent with rich toolset for deep interaction with post-simulation environment
5. **Deep Interaction**: Chat with any agent in the simulated world & Interact with ReportAgent

## 🚀 Quick Start

### Prerequisites

> Note: Fishi was developed and tested on Mac and Linux. Windows compatibility is experimental.

| Tool | Version | Description | Check Installation |
|------|---------|-------------|-------------------|
| **Bun** | Latest | Fast JavaScript runtime & package manager | `bun -v` |
| **Python** | 3.11+ | Backend runtime | `python --version` |
| **uv** | Latest | Python package manager | `uv --version` |
| **Docker** | Latest | For Neo4j database | `docker --version` |

### 1. Start Neo4j Database

```bash
# Start Neo4j using Docker Compose
docker-compose up -d

# Neo4j Browser available at: http://localhost:7474
# Default credentials: neo4j / mirofish123
```

### 2. Configure Environment Variables

```bash
# Copy the example configuration file
cp .env.example .env

# Edit the .env file and fill in the required API keys
```

**Required Environment Variables:**

```env
# LLM API Configuration (supports any LLM with OpenAI SDK format)
# Recommended: Use a capable model like GPT-4, Claude, or Qwen
LLM_API_KEY=your_api_key
LLM_BASE_URL=https://api.openai.com/v1
LLM_MODEL_NAME=gpt-4

# Neo4j Graph Database Configuration
# Use Docker Compose to start local Neo4j: docker-compose up -d
NEO4J_URI=bolt://localhost:7687
NEO4J_USERNAME=neo4j
NEO4J_PASSWORD=mirofish123
NEO4J_DATABASE=neo4j
```

### 3. Install Dependencies

```bash
# One-click installation of all dependencies (root + frontend + backend)
bun run setup:all
```

Or install step by step:

```bash
# Install dependencies (root + frontend)
bun install

# Install Python dependencies (auto-creates virtual environment)
bun run setup:backend
```

### 4. Start Services

```bash
# Start both frontend and backend (run from project root)
bun dev
```

**Service URLs:**
- Frontend: `http://localhost:3000`
- Backend API: `http://localhost:5001`

**Start Individually:**

```bash
bun run backend   # Start backend only
bun run frontend  # Start frontend only
```

## 🛠️ Tech Stack

- **Frontend**: Vue 3 + Vite + TypeScript
- **Backend**: Python + Flask
- **Database**: Neo4j (Graph Database)
- **Simulation**: OASIS (Open Agent Social Interaction Simulations)
- **LLM Integration**: OpenAI-compatible API

## 📄 Acknowledgments

Fishi's core simulation engine is powered by **[OASIS (Open Agent Social Interaction Simulations)](https://github.com/camel-ai/oasis)**. OASIS is a high-performance social media simulation framework developed by the [CAMEL-AI](https://github.com/camel-ai) team, supporting million-scale agent interaction simulations, providing a solid technical foundation for Fishi's swarm intelligence emergence. We sincerely thank the CAMEL-AI team for their open-source contributions!

## 📝 License

This project is licensed under the Apache 2.0 License - see the [LICENSE](LICENSE) file for details.