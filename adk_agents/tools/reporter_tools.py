"""
ADK Tools for Report Generation
"""

import os
import re
import json
from datetime import datetime
from google.adk.tools.tool_context import ToolContext
from adk_agents.state_manager import update_step_progress_state, get_state_manager, get_active_session_id, save_current_state
import config


def _build_relationship_tree(relationships: list) -> dict:
    """Parses flat relationship strings into a parent-child tree mapping."""
    tree = {}
    child_to_parents = {}
    
    for rel in relationships:
        try:
            # Format: "child.col → parent.id"
            parts = rel.split(" → ")
            if len(parts) != 2:
                continue
                
            child_table = parts[0].split(".")[0].strip()
            parent_table = parts[1].split(".")[0].strip()
            
            if parent_table not in tree:
                tree[parent_table] = []
            if child_table not in tree[parent_table]:
                tree[parent_table].append(child_table)
                
            if child_table not in child_to_parents:
                child_to_parents[child_table] = []
            child_to_parents[child_table].append(parent_table)
        except Exception as e:
            from adk_agents.tools.error_utils import log_and_raise_connection_error
            log_and_raise_connection_error("Error building relationship tree", e)
            
    # Identify roots (tables that have children but are not themselves children)
    roots = [t for t in tree if t not in child_to_parents]
    
    # If everything is interconnected (circular or multiple roots), take all unique parents as potential starts
    if not roots:
        roots = sorted(list(tree.keys()))
        
    return {"tree": tree, "roots": roots}


def _render_tree_node(table: str, tree: dict, prefix: str = "", is_last: bool = True, visited=None) -> list:
    """Recursively renders a tree node with box-drawing characters."""
    if visited is None:
        visited = set()
    
    # Avoid infinite recursion in case of circular relationships
    if table in visited:
        return [f"{prefix}{'└── ' if is_last else '├── '}{table} (circular)"]
    visited.add(table)
    
    marker = "└── " if is_last else "├── "
    lines = [f"{prefix}{marker}{table}"]
    
    children = tree.get(table, [])
    if children:
        new_prefix = prefix + ("    " if is_last else "│   ")
        for i, child in enumerate(sorted(children)):
            is_child_last = (i == len(children) - 1)
            lines.extend(_render_tree_node(child, tree, new_prefix, is_child_last, visited.copy()))
            
    return lines


def _build_markdown_report_lines(state: dict, schema: dict, relationships: list, changes: list, llm_insights: str, impact_results: list, custom_findings: list, pii_alerts: list) -> list:
    """Helper to build all markdown lines for the report from state."""
    lines = [
        "# 📊 Database Report",
        "",
        f"**Generated:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"**Database:** {getattr(config, 'DB_TYPE', 'Unknown').upper()}",
        "",
        "---",
        "",
    ]

    # LLM Insights
    if llm_insights:
        from adk_agents.tools.llm_insights_tools import format_insights_for_report
        lines += [format_insights_for_report(llm_insights), "---", ""]

    # Relationships
    lines += ["## 🔗 Table Relationships", ""]
    if relationships:
        # Visual Tree Structure
        lines += ["### 🌳 Database Relationship Hierarchy", ""]
        lines.append("```text")
        tree_data = _build_relationship_tree(relationships)
        tree = tree_data["tree"]
        roots = tree_data["roots"]
        
        for i, root in enumerate(sorted(roots)):
            # Root level nodes
            marker = "── "
            lines.append(root)
            children = tree.get(root, [])
            for j, child in enumerate(sorted(children)):
                is_last = (j == len(children) - 1)
                lines.extend(_render_tree_node(child, tree, "", is_last))
            if i < len(roots) - 1:
                lines.append("")
        
        lines.append("```")
        lines.append("")
        
        # Detailed List
        lines += ["### 📋 Detailed Relationship List", ""]
        for rel in relationships:
            lines.append(f"- `{rel}`")
    else:
        lines.append("_No relationships detected._")
    lines += ["", "---", ""]

    # Schema Drift
    lines += ["## 🚨 Changes Since Last Run", ""]
    if changes:
        for item in changes:
            lines.append(f"- {item}")
    else:
        lines.append("_No changes detected._")
    lines += ["", "---", ""]

    # Impact Analysis
    if impact_results:
        lines += ["## 🔎 Impact Analysis", ""]
        for result in impact_results:
            if "error" in result:
                lines.append(f"- ⚠️ {result['error']}")
                continue
            lines += [
                f"### Starting point: `{result.get('starting_point', 'Unknown')}`",
                "",
                "**Downstream (things that depend on this):**",
            ]
            downstream = result.get("downstream_affected", [])
            lines += [f"- `{d}`" for d in downstream] or ["_Nothing depends on this._"]
            lines += ["", "**Upstream (things this depends on):**"]
            upstream = result.get("upstream_dependencies", [])
            lines += [f"- `{u}`" for u in upstream] or ["_This has no dependencies._"]
            lines.append("")

    # Custom Ad-hoc Findings
    if custom_findings:
        lines += ["## 💡 Custom Analysis - User-Requested Insights", ""]
        for finding in custom_findings:
            title = finding.get('title', finding.get('description', 'Custom Query'))
            
            lines += [f"### {title}", ""]
            
            results = finding.get("results", [])
            if results:
                # Markdown table headers
                cols = list(results[0].keys())
                lines.append("| " + " | ".join(cols) + " |")
                lines.append("| " + " | ".join(["---"] * len(cols)) + " |")
                
                # Markdown table rows
                for row in results:
                    lines.append("| " + " | ".join(str(row.get(c, "")) for c in cols) + " |")
            else:
                # Provide context if the table itself might be empty
                table_match = re.search(r'FROM\s+"?([^"\s]+)"?', finding.get("query", ""), re.IGNORECASE)
                table_name = table_match.group(1) if table_match else None
                row_count = schema.get(table_name, {}).get("row_count", 0) if table_name else 0
                
                if table_name and row_count == 0:
                    lines.append(f"_No results returned (Table `{table_name}` is currently empty)._")
                else:
                    lines.append("_No results returned for this query._")
            lines.append("")
        lines += ["---", ""]

    # Security & PII Audit
    if pii_alerts:
        lines += ["## 🛡️ Security & Privacy Audit (PII Detection)", ""]
        lines += ["> [!WARNING]", "> Important: The following sensitive data patterns were detected in the database sampling.", ""]
        
        lines.append("| Table | Column | PII Type | Severity | Confidence |")
        lines.append("| --- | --- | --- | --- | --- |")
        for alert in pii_alerts:
            lines.append(f"| {alert.get('table')} | {alert.get('column')} | {alert.get('type')} | **{alert.get('severity')}** | {alert.get('confidence')} |")
        
        lines += ["", "---", ""]

    return lines


def _build_json_report_data(schema: dict, relationships: list, changes: list, llm_insights: str, impact_results: list, custom_findings: list, total_rows: int, pii_alerts: list) -> dict:
    """Helper to build the dictionary structure for the JSON report."""
    return {
        "timestamp": datetime.now().isoformat(),
        "database_type": getattr(config, 'DB_TYPE', 'Unknown'),
        "summary": {
            "total_tables": len(schema),
            "total_rows": total_rows,
            "total_relationships": len(relationships),
        },
        "schema": schema,
        "relationships": relationships,
        "drift": changes,
        "impact_analysis": impact_results,
        "llm_insights": llm_insights,
        "custom_findings": custom_findings,
        "pii_alerts": pii_alerts,
    }



def generate_comprehensive_report(tool_context: ToolContext) -> dict:
    """
    Generates both Markdown and JSON reports in one call with the same timestamp.

    Args:
        tool_context (ToolContext): ADK context with session state

    Returns:
        dict: Combined report generation status
    """
    try:
        # Generate a single timestamp for both reports
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        session_id = (getattr(tool_context, 'session_id', None)
                      or get_active_session_id()
                      or str(id(tool_context.state)))

        state_manager = get_state_manager()
        state = state_manager.load_state(session_id) or {}

        for k, v in state.items():
            tool_context.state[k] = v

        schema = state.get("schema", {})
        relationships = state.get("relationships", [])
        changes = state.get("changes", [])
        llm_insights = state.get("llm_insights")
        custom_findings = state.get("custom_findings", [])
        pii_alerts = state.get("pii_alerts", [])

        impact_results = []
        if "impact_analysis" in state:
            impact_results = [state["impact_analysis"]]
        elif "impact_results" in state:
            impact_results = state["impact_results"]

        if not schema:
            return {"status": "error", "message": "No schema found in session state."}

        total_rows = sum(info.get("row_count", 0) for info in schema.values() if isinstance(info.get("row_count"), (int, float)))

        report_dir = getattr(config, 'REPORT_DIR', 'reports')
        md_dir = os.path.join(report_dir, 'markdown')
        json_dir = os.path.join(report_dir, 'json')
        
        os.makedirs(md_dir, exist_ok=True)
        os.makedirs(json_dir, exist_ok=True)

        report_path = os.path.join(md_dir, f"db_report_{timestamp}.md")
        json_path = os.path.join(json_dir, f"db_intelligence_{timestamp}.json")

        lines = _build_markdown_report_lines(state, schema, relationships, changes, llm_insights, impact_results, custom_findings, pii_alerts)


        # Write Markdown
        try:
            with open(report_path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            print(f"   - 📑 Markdown report saved to: {report_path}")
        except (PermissionError, OSError) as e:
            return {"status": "error", "error": str(e), "message": str(e)}

        # Generate JSON report
        report_data = _build_json_report_data(schema, relationships, changes, llm_insights, impact_results, custom_findings, total_rows, pii_alerts)

        try:
            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(report_data, f, indent=4)
            print(f"   - 📁 JSON report saved to: {json_path}")
        except (PermissionError, OSError) as e:
            print(f"   - Error saving JSON report: {e}")
            # Non-fatal error for the whole tool, but worth noting
        
        # Save paths to session state
        state["report_path"]      = report_path
        state["json_report_path"] = json_path
        
        # Merging local state changes back into tool_context for consistency
        for k, v in state.items():
            tool_context.state[k] = v

        update_step_progress_state(state, "report_generation", session_id)
        save_current_state(tool_context)

        return {
            "status": "success",
            "markdown_report": report_path,
            "json_report": json_path,
            "message": f"Generated both reports with timestamp {timestamp}: {report_path} and {json_path}"
        }

    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "message": f"Failed to generate comprehensive report: {str(e)}"
        }
