#!/bin/bash
# PaperOrchestra Project Scaffolder
# Usage: ./scaffold.sh <project_name>

PROJECT_NAME=$1

if [ -z "$PROJECT_NAME" ]; then
    echo "Usage: ./scaffold.sh <project_name>"
    exit 1
fi

# Create directory structure
mkdir -p "$PROJECT_NAME/sections"
mkdir -p "$PROJECT_NAME/assets"
mkdir -p "$PROJECT_NAME/notes"

# Create idea.md Template
cat > "$PROJECT_NAME/idea.md" <<EOF
# Project Idea: $PROJECT_NAME

## 1. Thesis
<!-- Define your core argument or problem space here -->

## 2. Core Methodology
<!-- Describe your proposed solution, algorithm, or research approach -->

## 3. Evidence/Log Summary
<!-- Provide key data points, ablation results, or experimental observations -->

## 4. Specific Gaps & Questions
<!-- What specific sub-fields or competitor limitations should the Search Agent focus on? -->

## 5. Tacit Knowledge / Nuances
<!-- Any expert insights that aren't available in training data? -->
EOF

# Create metadata.json Boilerplate
cat > "$PROJECT_NAME/metadata.json" <<EOF
{
  "slug": "$(echo $PROJECT_NAME | tr '[:upper:]' '[:lower:]' | tr ' ' '-')",
  "title": "$PROJECT_NAME",
  "authors": [],
  "date": "$(date +%Y-%m-%d)",
  "abstract": "",
  "plan": {
    "visualization_plan": [],
    "literature_search_strategy": {
      "macro": [],
      "micro": []
    },
    "section_plan": []
  },
  "references": []
}
EOF

# Create instructions
cat > "$PROJECT_NAME/README.md" <<EOF
# PaperOrchestra Project: $PROJECT_NAME

1.  **Phase 0 (Interview)**: Use the IM channel to refine your ideas. Every update will be saved to \`idea.md\`.
2.  **Phase 1 (Planning)**: Run the Outline Agent to populate the \`plan\` in \`metadata.json\`.
3.  **Phase 2 (Discovery)**: Run the Search Agent to build the \`references\` bank.
4.  **Phase 3 (Drafting)**: Sections will be generated individually in the \`sections/\` folder.
5.  **Phase 4 (Refinement)**: Assemble and refine into \`content.md\`.
EOF

echo "[DONE] Project $PROJECT_NAME initialized successfully."
EOF
chmod +x "$PROJECT_NAME/scaffold.sh" # No, it should be in the skill scripts folder
