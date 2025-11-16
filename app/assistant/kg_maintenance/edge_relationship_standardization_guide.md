# Edge Relationship Standardization Guide

## 🎯 **Philosophy: Preserve Nuance, Reduce Noise**

The goal of edge relationship standardization is to **reduce noise** while **preserving important semantic distinctions**. We want to catch common AI agent mistakes without losing the subtle differences that matter.

## 🔍 **Key Principles**

### 1. **Preserve Semantic Distinctions**
- `works_for` ≠ `works_at` (employment vs. location)
- `based_in` ≠ `located_in` (organization base vs. general location)
- `parent_of` ≠ `child_of` (direction matters)

### 2. **Standardize Common Variations**
- `is_married_to` → `married_to` (remove unnecessary "is_")
- `employed_by` → `works_for` (employment relationship)
- `resides_in` → `lives_in` (residence relationship)

### 3. **Maintain Context-Specific Relationships**
- Keep domain-specific relationships separate
- Don't over-generalize specialized terms

## 📊 **Relationship Categories**

### **Family Relationships**
```
Marriage: is_married_to → married_to
Parent-Child: is_parent_of → parent_of
Child-Parent: child_of → child_of (preserves direction!)
Sibling: brother_of → sibling_of
```

### **Work Relationships**
```
Employment: employed_by → works_for
Location: works_at → works_at (preserved!)
Management: is_manager_of → manages
Reporting: supervised_by → reports_to
```

### **Location Relationships**
```
Residence: resides_in → lives_in
General Location: is_located_in → located_in
Organization Base: headquartered_in → based_in
```

### **Possession Relationships**
```
General: owns → has
Specific: has_phone → has_phone (preserved!)
```

## ⚠️ **Important Distinctions Preserved**

### **1. Direction Matters**
- `parent_of` ≠ `child_of`
- `manages` ≠ `reports_to`
- `gives_to` ≠ `receives_from`

### **2. Context Matters**
- `works_at` (location) ≠ `works_for` (employment)
- `based_in` (organization base) ≠ `located_in` (general location)
- `father_of` (specific) → `parent_of` (general, but still parent-child)

### **3. Specificity Matters**
- `has_phone` (kept specific)
- `has_email` (kept specific)
- `has_address` (kept specific)

## 🛠️ **Usage Guidelines**

### **When to Standardize**
- Common AI agent variations (`is_married_to` → `married_to`)
- Synonyms that mean the same thing (`employed_by` → `works_for`)
- Minor formatting differences (`has_spouse` → `married_to`)

### **When NOT to Standardize**
- Different semantic meanings (`works_at` vs `works_for`)
- Directional relationships (`parent_of` vs `child_of`)
- Domain-specific terms that should remain distinct

### **Confidence Thresholds**
- **High Confidence (0.8-1.0)**: Clear synonyms, safe to standardize
- **Medium Confidence (0.5-0.8)**: Related but distinct, use with caution
- **Low Confidence (0.1-0.5)**: Keep original, don't standardize

## 📈 **Monitoring and Improvement**

### **Track Usage Patterns**
- Which mappings are used most?
- Which relationships are frequently guessed incorrectly?
- Are there new patterns emerging?

### **Review Low-Confidence Cases**
- Relationships with low confidence scores
- Mappings that are rarely used
- Potential new mappings to add

### **Domain-Specific Customization**
- Add mappings for your specific domain
- Preserve domain-specific terminology
- Don't over-generalize specialized terms

## 🔧 **Example: Adding Custom Mappings**

```python
# Good: Preserves nuance
standardizer.add_mapping(
    guessed_relationship="uses_technology",
    canonical_relationship="uses",  # General possession
    confidence_score=95
)

# Good: Keeps specific relationship
standardizer.add_mapping(
    guessed_relationship="implements_system",
    canonical_relationship="implements_system",  # Keep specific
    confidence_score=100
)

# Bad: Loses important distinction
# DON'T: "works_at" → "works_for" (loses location context)
```

## 🎯 **Best Practices**

1. **Start Conservative**: Only standardize clear synonyms
2. **Test Thoroughly**: Verify mappings don't lose important context
3. **Monitor Usage**: Track which mappings are actually helpful
4. **Iterate Carefully**: Add new mappings based on observed patterns
5. **Document Decisions**: Keep track of why certain mappings were chosen

## 🚨 **Common Pitfalls to Avoid**

1. **Over-Generalization**: Don't lose important distinctions
2. **Direction Confusion**: Don't mix up directional relationships
3. **Context Loss**: Don't standardize away important context
4. **Domain Ignorance**: Don't standardize domain-specific terms
5. **Confidence Inflation**: Don't set confidence too high for uncertain mappings

Remember: **Better to keep a relationship as-is than to standardize it incorrectly!**
