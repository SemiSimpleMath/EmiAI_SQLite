# KG Pipeline V2 - Independent Stage Processing

This is a complete rewrite of the KG pipeline to support independent stage processing.

## 🎯 **Design Goals**

1. **Stage Independence**: Each stage can run separately (different days)
2. **Data Preservation**: All intermediate results stored in database
3. **Fault Tolerance**: Can restart any stage independently
4. **Scalability**: Can run stages on different machines
5. **Parallel Ready**: Foundation for future parallel processing

## 🏗️ **Architecture**

### **Stage Flow**
```
Raw Data → Stage 1 (Fact Extraction) → Stage 2 (Parser) → Stage 3 (Metadata) → Stage 4 (Merge) → Stage 5 (Taxonomy) → Final KG
```

### **Data Model**
- **Node Data**: Complete node information (label, type, original_sentence, etc.)
- **Edge Data**: Relationships between nodes
- **Stage Results**: Intermediate results from each stage
- **Provenance**: Track data lineage through stages

## 📊 **Database Schema**

### **Core Tables**
- `pipeline_nodes`: Complete node data for processing
- `pipeline_edges`: Edge data for processing  
- `stage_results`: Intermediate results from each stage
- `stage_completion`: Track which stages are complete for each node
- `pipeline_batches`: Organize processing into batches

### **Stage-Specific Tables**
- `fact_extraction_results`: Facts extracted from nodes
- `parser_results`: Parsed entities and relationships
- `metadata_results`: Enriched metadata
- `merge_results`: Merged node/edge data
- `taxonomy_results`: Taxonomy classifications

## 🚀 **Usage**

### **Run Individual Stages**
```bash
# Stage 1: Fact Extraction
python run_stage.py --stage fact_extraction --batch-size 100

# Stage 2: Parser
python run_stage.py --stage parser --batch-size 100

# Stage 3: Metadata
python run_stage.py --stage metadata --batch-size 100
```

### **Check Stage Status**
```bash
python check_pipeline_status.py
```

### **Resume Failed Stages**
```bash
python run_stage.py --stage metadata --resume-failed
```

## 🔧 **Implementation Status**

- [ ] Database schema design
- [ ] Stage 1: Fact Extraction
- [ ] Stage 2: Parser  
- [ ] Stage 3: Metadata
- [ ] Stage 4: Merge
- [ ] Stage 5: Taxonomy
- [ ] Pipeline coordination
- [ ] Error handling and recovery
- [ ] Performance monitoring
