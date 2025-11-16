# Knowledge Graph Documentation Index

## 📚 Complete Documentation Suite

This directory contains **8 comprehensive documents** covering every aspect of the Emi Knowledge Graph system, including the multi-agent manager architecture.

---

## 🚀 Start Here

### [README.md](./README.md) - 9.6 KB
**The entry point for all KG documentation**

- Quick start guide
- System overview
- Common use cases
- Configuration basics
- Monitoring queries
- Development guidelines

**Best for:** First-time users, quick reference

---

## 📖 Core Documentation

### [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) - 16.4 KB
**Complete system architecture and design**

**Contents:**
- System architecture diagram
- Two-stage pipeline overview (Entity Resolution + Knowledge Extraction)
- Agent ecosystem (8 agents)
- Database schema overview
- Processing flow diagrams
- Key features and capabilities
- Configuration overview
- Performance considerations
- Future enhancements

**Best for:** Understanding the big picture, system design, architecture decisions

**Key Sections:**
- ✅ System Architecture (visual diagram)
- ✅ Stage 1 vs Stage 2 comparison
- ✅ Database schema summary
- ✅ Agent roles overview
- ✅ Performance characteristics
- ✅ Configuration basics

---

## 🔍 Stage-Specific Documentation

### [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md) - 13.4 KB
**Stage 1: Entity Resolution preprocessing layer**

**Contents:**
- Purpose and architecture of Stage 1
- Overlapping chunk strategy
- Entity resolver agent deep dive
- HTML filtering logic
- Database tables (unified_log → processed_entity_log)
- Configuration and tuning
- Performance metrics
- Examples and best practices

**Best for:** Understanding pronoun resolution, debugging Stage 1 issues, tuning chunk sizes

**Key Sections:**
- ✅ Why entity resolution matters
- ✅ Overlapping window strategy (8 msgs + 3 overlap)
- ✅ Entity resolver agent behavior
- ✅ HTML filtering rules
- ✅ Database schema details
- ✅ Configuration trade-offs
- ✅ Performance optimization

**Example Flow:**
```
Input:  "I want to work on it tomorrow"
Output: "Jukka wants to work on the Emi UI tomorrow"
```

---

### [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md) - 21.3 KB
**Stage 2: Knowledge Graph extraction pipeline**

**Contents:**
- Adaptive window processing (20-message windows)
- Multi-agent pipeline (7 agents in Stage 2)
- Conversation boundary detection
- Atomic sentence parsing
- Fact extraction process
- Metadata enrichment
- Smart merging strategies
- Database commit flow
- Data integrity checks

**Best for:** Understanding knowledge extraction, debugging Stage 2 issues, tuning extraction quality

**Key Sections:**
- ✅ Adaptive window strategy
- ✅ Conversation boundary detection
- ✅ Parsing and fact extraction
- ✅ Metadata enrichment (temporal data)
- ✅ Node merging logic
- ✅ Edge merging logic
- ✅ Commit and transaction handling
- ✅ Error handling

**Example Flow:**
```
Input:  "Jukka wants to work on the Emi UI tomorrow"
Output: 
  Node: Jukka (Entity, Person)
  Node: Emi UI (Goal, Feature)
  Edge: Jukka --[WantsToWorkOn]--> Emi UI
  Metadata: start_date=tomorrow, confidence=0.85
```

---

## 🤖 Agent Documentation

### [KG_AGENTS.md](./KG_AGENTS.md) - 22.6 KB
**Complete reference for all 8 AI agents**

**Contents:**

**Stage 1 Agents:**
1. **entity_resolver** - Pronoun and reference resolution

**Stage 2 Agents:**
2. **conversation_boundary** - Conversation segmentation
3. **parser** - Atomic sentence extraction
4. **fact_extractor** - Node and edge extraction
5. **meta_data_add** - Temporal metadata enrichment
6. **node_merger** - Merge decision making
7. **node_data_merger** - Intelligent data combination
8. **edge_merger** - Edge merge decisions

**For each agent:**
- Purpose and registry name
- Input/output schemas (with examples)
- Decision criteria and behavior
- Examples with reasoning
- Prompt strategies
- Performance characteristics

**Best for:** Understanding agent behavior, debugging agent decisions, customizing agents

**Key Sections:**
- ✅ Complete agent specifications
- ✅ Input/output schemas
- ✅ Decision examples
- ✅ Agent interaction patterns
- ✅ Performance benchmarks
- ✅ Debugging guide

---

## ⚡ Quick Reference

### [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) - 13.8 KB
**Cheatsheet for common operations**

**Contents:**
- System overview (visual)
- Quick commands (copy-paste ready)
- Agent summary table
- Database schema cheatsheet
- Node types reference
- Configuration cheatsheet
- Monitoring queries (SQL)
- Common patterns
- Troubleshooting guide
- Performance benchmarks
- Best practices checklist

**Best for:** Day-to-day operations, quick lookups, SQL queries, troubleshooting

**Key Sections:**
- ✅ Quick command reference
- ✅ 8 agents at a glance (table)
- ✅ Database schema summary
- ✅ Configuration cheatsheet
- ✅ Monitoring SQL queries
- ✅ Troubleshooting table
- ✅ Best practices DO/DON'T
- ✅ Pipeline flow summary

---

## 📊 Documentation Statistics

| Document | Size | Focus | Audience |
|----------|------|-------|----------|
| README.md | 9.6 KB | Overview & getting started | Everyone |
| KG_ARCHITECTURE.md | 16.4 KB | System design | Architects, developers |
| KG_ENTITY_RESOLUTION.md | 13.4 KB | Stage 1 details | Stage 1 developers |
| KG_PIPELINE_DETAILS.md | 21.3 KB | Stage 2 details | Stage 2 developers |
| KG_AGENTS.md | 22.6 KB | Agent reference | Agent developers |
| KG_QUICK_REFERENCE.md | 13.8 KB | Cheatsheet | Daily users |
| KG_CRITICAL_ANALYSIS.md | 18.7 KB | System critique | Tech leads, architects |
| MULTI_AGENT_MANAGERS.md | 25.2 KB | Manager architecture | System architects |
| **TOTAL** | **~140 KB** | **Complete system** | **All stakeholders** |

---

## 🎯 Documentation Paths by Use Case

### "I'm new to the KG system"
1. Start: [README.md](./README.md)
2. Then: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md)
3. Quick reference: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md)

### "I need to run the pipeline"
1. Quick start: [README.md](./README.md) → "Quick Start" section
2. Commands: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Quick Commands"
3. Monitoring: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Monitoring Queries"

### "I'm debugging Stage 1 issues"
1. Stage 1: [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md)
2. Agent: [KG_AGENTS.md](./KG_AGENTS.md) → "Entity Resolver Agent"
3. Troubleshoot: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Troubleshooting"

### "I'm debugging Stage 2 issues"
1. Stage 2: [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md)
2. Agents: [KG_AGENTS.md](./KG_AGENTS.md) → Stage 2 agents
3. Troubleshoot: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Troubleshooting"

### "I need to tune performance"
1. Architecture: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) → "Performance Considerations"
2. Configuration: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Configuration Cheatsheet"
3. Benchmarks: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Performance Benchmarks"

### "I'm developing new features"
1. Architecture: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md)
2. Stage details: [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md) + [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md)
3. Agent details: [KG_AGENTS.md](./KG_AGENTS.md)
4. Manager architecture: [MULTI_AGENT_MANAGERS.md](./MULTI_AGENT_MANAGERS.md)
5. Development: [README.md](./README.md) → "Development"

### "I need SQL queries"
1. Quick ref: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Monitoring Queries"
2. Architecture: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) → "Monitoring & Debugging"
3. Examples: [README.md](./README.md) → "Common Use Cases"

### "I'm customizing agents"
1. Agent details: [KG_AGENTS.md](./KG_AGENTS.md)
2. Manager architecture: [MULTI_AGENT_MANAGERS.md](./MULTI_AGENT_MANAGERS.md)
3. Pipeline integration: [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md)
4. Development: [README.md](./README.md) → "Development"

### "I'm building a new manager"
1. Start: [MULTI_AGENT_MANAGERS.md](./MULTI_AGENT_MANAGERS.md)
2. Examples: [daily_summary_manager.md](../../daily_summary_manager.md)
3. Agent design: [KG_AGENTS.md](./KG_AGENTS.md)
4. Best practices: [MULTI_AGENT_MANAGERS.md](./MULTI_AGENT_MANAGERS.md) → "Best Practices"

---

## 📋 Coverage Matrix

| Topic | Architecture | Entity Resolution | Pipeline Details | Agents | Quick Ref | README |
|-------|:------------:|:-----------------:|:----------------:|:------:|:---------:|:------:|
| System Overview | ✅✅✅ | ✅ | ✅ | - | ✅✅ | ✅✅✅ |
| Stage 1 Details | ✅ | ✅✅✅ | - | ✅ | ✅ | ✅ |
| Stage 2 Details | ✅ | - | ✅✅✅ | ✅ | ✅ | ✅ |
| Agent Details | ✅ | ✅ | ✅ | ✅✅✅ | ✅✅ | - |
| Database Schema | ✅✅ | ✅✅ | ✅ | - | ✅✅ | ✅ |
| Configuration | ✅✅ | ✅✅ | ✅✅ | - | ✅✅✅ | ✅ |
| Performance | ✅✅ | ✅✅ | ✅✅ | ✅ | ✅✅✅ | ✅ |
| SQL Queries | ✅ | - | - | - | ✅✅✅ | ✅✅ |
| Examples | ✅ | ✅✅✅ | ✅✅✅ | ✅✅✅ | ✅✅ | ✅✅ |
| Troubleshooting | ✅ | ✅✅ | ✅✅ | ✅ | ✅✅✅ | ✅ |
| Best Practices | ✅ | ✅✅ | ✅✅ | ✅ | ✅✅✅ | ✅✅ |

Legend: ✅ = covered, ✅✅ = detailed, ✅✅✅ = comprehensive

---

## 🔗 Cross-References

### Database Schema
- Primary: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) → "Database Schema"
- Quick ref: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Database Tables"
- Stage 1: [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md) → "Database Tables"

### Configuration
- Overview: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) → "Configuration"
- Stage 1: [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md) → "Configuration"
- Stage 2: [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md) → "Configuration"
- Quick ref: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Configuration Cheatsheet"

### Agents
- Overview: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) → "Agent Ecosystem"
- Complete: [KG_AGENTS.md](./KG_AGENTS.md)
- Quick ref: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "8 Agents at a Glance"

### Performance
- Overview: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) → "Performance Considerations"
- Stage 1: [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md) → "Performance Metrics"
- Stage 2: [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md) → "Performance Optimizations"
- Quick ref: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) → "Performance Benchmarks"

---

## 📝 Documentation Maintenance

### When to Update

**Architecture changes:**
- Update: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md)
- Update: [README.md](./README.md)
- Consider: All other docs

**Stage 1 changes:**
- Update: [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md)
- Update: [KG_AGENTS.md](./KG_AGENTS.md) (entity_resolver section)
- Update: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) (if config/commands changed)

**Stage 2 changes:**
- Update: [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md)
- Update: [KG_AGENTS.md](./KG_AGENTS.md) (relevant agent sections)
- Update: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) (if config/commands changed)

**Agent changes:**
- Update: [KG_AGENTS.md](./KG_AGENTS.md) (primary)
- Update: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) (agent table)
- Consider: Stage-specific docs

**Database schema changes:**
- Update: [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) (primary)
- Update: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) (schema cheatsheet)
- Update: Stage-specific docs (if tables changed)

**Configuration changes:**
- Update: All docs mentioning the changed config
- Update: [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) (config cheatsheet)

---

## 🎓 Learning Path

### Beginner (Day 1-2)
1. ✅ [README.md](./README.md) - Get oriented
2. ✅ [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md) - Understand system
3. ✅ [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md) - Quick commands
4. ✅ Run the pipeline with small batch
5. ✅ Monitor with SQL queries

### Intermediate (Week 1)
1. ✅ [KG_ENTITY_RESOLUTION.md](./KG_ENTITY_RESOLUTION.md) - Deep dive Stage 1
2. ✅ [KG_PIPELINE_DETAILS.md](./KG_PIPELINE_DETAILS.md) - Deep dive Stage 2
3. ✅ [KG_AGENTS.md](./KG_AGENTS.md) - Understand agents
4. ✅ Experiment with configuration
5. ✅ Debug issues using docs

### Advanced (Month 1)
1. ✅ Review all agent prompt templates
2. ✅ Customize agent behavior
3. ✅ Optimize performance
4. ✅ Develop new features
5. ✅ Contribute to documentation

---

## ✨ Documentation Features

### What Makes This Documentation Suite Great

✅ **Comprehensive** - 97KB covering every aspect  
✅ **Well-Organized** - Clear structure and cross-references  
✅ **Example-Rich** - Real examples throughout  
✅ **Actionable** - Copy-paste commands and queries  
✅ **Visual** - Diagrams and tables  
✅ **Searchable** - Detailed index and cross-references  
✅ **Maintainable** - Clear update guidelines  
✅ **Progressive** - From beginner to advanced  

---

## 🔍 Search Guide

Can't find something? Try these:

1. **Search by keyword** in this index
2. **Check quick reference** - [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md)
3. **Check README** - [README.md](./README.md)
4. **Search all docs** - Full-text search in your editor
5. **Check cross-references** - Links throughout docs

Common search terms:
- "agent" → [KG_AGENTS.md](./KG_AGENTS.md)
- "configuration" → [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md)
- "database" → [KG_ARCHITECTURE.md](./KG_ARCHITECTURE.md)
- "performance" → [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md)
- "SQL" → [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md)
- "example" → All docs have examples
- "troubleshoot" → [KG_QUICK_REFERENCE.md](./KG_QUICK_REFERENCE.md)

---

**Last Updated:** September 29, 2025  
**Documentation Version:** 1.0  
**Total Pages:** 6 documents, 97KB
