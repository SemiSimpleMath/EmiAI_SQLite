from datetime import datetime, timezone
from typing import Dict, Any, Optional, List, Union
import uuid

from pydantic import BaseModel, Field
from sqlalchemy import or_, desc

from app.assistant.lib.core_tools.base_tool.base_tool import BaseTool
from app.assistant.utils.pydantic_classes import ToolResult, ToolMessage

from app.assistant.kg_core.knowledge_graph_db_sqlite import Node, Edge
from app.assistant.kg_core.kg_tools import semantic_find_node_by_text, short_describe_node, describe_edge, build_temporal_subgraph

from app.assistant.utils.logging_config import get_logger
from sqlalchemy.orm import Session
from app.models.base import get_session

logger = get_logger(__name__)


class SearchFilters(BaseModel):
    """Filters to restrict search scope with proper validation and guidance."""
    node_types: Union[List[str], None] = Field(None, description="List of node types to filter by (e.g., 'Entity', 'Goal', 'State')")
    start_date: Union[str, None] = Field(None, description="ISO date string - only include nodes valid after this date (e.g., '2024-01-01T00:00:00Z')")
    end_date: Union[str, None] = Field(None, description="ISO date string - only include nodes valid before this date (e.g., '2024-12-31T23:59:59Z')")
    node_id: Union[str, None] = Field(None, description="UUID of a single node to restrict search to its neighborhood")
    max_hops: Union[int, None] = Field(None, description="Integer - expand from node_id to neighbors within this many hops (requires node_id, default=all connected)")
    text: Union[str, None] = Field(None, description="Text to filter nodes by (searches in node labels)")
    taxonomy_paths: Union[List[str], None] = Field(None, description="List of taxonomy paths to filter by (e.g., 'entity > person', 'state > educational_status'). Returns union of nodes from all specified paths.")


class kg_find_node_args(BaseModel):
    """Arguments for the find_node tool call."""
    text: str
    threshold: float
    k: int
    node_id: str
    edges_k: int
    node_types: List[str]
    start_date: str
    end_date: str
    max_hops: int
    taxonomy_paths: List[str] = Field(default_factory=list)



def _recency_score(ts: Optional[datetime]) -> float:
    if not ts:
        return 0.0
    now = datetime.now(timezone.utc)
    age_days = max(0.0, (now - ts).total_seconds() / 86400.0)
    half_life = 90.0
    return 0.5 ** (age_days / half_life)

class KnowledgeGraphSearch(BaseTool):
    """
    Tool for querying and inspecting knowledge graph data,
    including semantic node search and node description.
    """

    def __init__(self):
        super().__init__('knowledge_graph_search')
        self.do_lazy_init = True
        self.session = None

    def lazy_init(self):
        self.session = get_session()
        self.do_lazy_init = False

    def execute(self, tool_message: ToolMessage) -> ToolResult:
        if self.do_lazy_init:
            self.lazy_init()

        try:
            logger.info("Executing KnowledgeGraphSearch")
            arguments = tool_message.tool_data.get('arguments', {})
            tool_name = tool_message.tool_data.get('tool_name')

            if not tool_name:
                raise ValueError("Missing tool_name in tool_data.")

            handler_method = getattr(self, f"handle_{tool_name}", None)
            if not handler_method:
                raise ValueError(f"Unsupported tool_name: {tool_name}")

            return handler_method(arguments, tool_message)

        except Exception as e:
            logger.exception("KnowledgeGraphTool execution failed")
            return self.publish_error(ToolResult(result_type="error", content=str(e)))

    def publish_result(self, result: ToolResult) -> ToolResult:
        return result

    def publish_error(self, error_result: ToolResult) -> ToolResult:
        return error_result

    # ---------------------- HANDLERS ----------------------

    def handle_kg_find_node(self, arguments: Dict[str, Any], tool_message: ToolMessage) -> ToolResult:
        try:
            # Validate arguments with the Pydantic model
            args = kg_find_node_args(**arguments)

            relaxed_filters_list = []
            results = []

            # Create filters from flattened arguments, handling empty values
            current_filters = SearchFilters(
                node_types=args.node_types if args.node_types else None,
                start_date=args.start_date if args.start_date else None,
                end_date=args.end_date if args.end_date else None,
                node_id=args.node_id if args.node_id else None,
                max_hops=args.max_hops if args.max_hops else None,
                taxonomy_paths=args.taxonomy_paths if args.taxonomy_paths else None
            )

            # 1. Initial search attempt with all filters
            logger.info(f"Attempting search with initial filters: {current_filters.model_dump_json(exclude_none=True)}")
            results = semantic_find_node_by_text(
                text=args.text,
                session=self.session,
                threshold=args.threshold,
                k=args.k,
                filters=current_filters
            )

            # 2. If no results, begin the relaxation process
            if not results:
                # Corrected relaxation order based on your ranking
                relaxation_plan = ["start_date", "end_date"]

                for filter_to_relax in relaxation_plan:
                    if getattr(current_filters, filter_to_relax) is not None:
                        setattr(current_filters, filter_to_relax, None)
                        relaxed_filters_list.append(filter_to_relax)

                        logger.info(f"Relaxed '{filter_to_relax}'. Retrying with filters: {current_filters.model_dump_json(exclude_none=True)}")

                        results = semantic_find_node_by_text(
                            text=args.text, session=self.session, threshold=args.threshold, k=args.k, filters=current_filters
                        )

                        if results:
                            break

            # --- Advanced Relaxation for max_hops ---
            # If there are still no results, you could implement logic to handle max_hops.
            # This would involve checking if max_hops was initially set, increasing it,
            # and re-running the search. For example:
            #
            # if not results and args.filters and args.filters.max_hops and args.filters.max_hops == 1:
            #     logger.info("Dropping filters failed. Now trying to expand max_hops to 2.")
            #     current_filters.max_hops = 2
            #     relaxed_filters_list.append("expanded 'max_hops' to 2")
            #     # NOTE: This assumes `semantic_find_node_by_text` can use max_hops.
            #     results = semantic_find_node_by_text(...)

            # 3. Build the output node cards
            output_nodes = []
            is_semantic_search = bool(args.text and args.text.strip())
            match_type = "semantic" if is_semantic_search else "filtered"
            
            for node, score in results:
                minimal_card = {
                    "node_id": str(node.id),
                    "label": node.label,
                    "description": node.description if hasattr(node, 'description') and node.description else None,
                    "node_type": getattr(node, 'node_type', None) or getattr(node, 'type_name', None),
                    "match": {"type": match_type, "score": round(float(score), 4) if is_semantic_search else None},
                    "start_date": node.start_date.isoformat() if node.start_date else None,
                    "end_date": node.end_date.isoformat() if node.end_date else None,
                    "start_date_confidence": node.start_date_confidence,
                    "end_date_confidence": node.end_date_confidence,
                }
                output_nodes.append(minimal_card)

            # 4. Construct the final human-readable message
            if is_semantic_search:
                content_message = f"Found {len(output_nodes)} node(s) for '{args.text}'"
            else:
                content_message = f"Found {len(output_nodes)} node(s) matching filters (no text search)"
            
            if relaxed_filters_list:
                constraints_str = ", ".join([f"'{f}'" for f in relaxed_filters_list])
                content_message += f". Note: The following constraints were relaxed to get results: {constraints_str}."

            # 5. Create the final data payload for the agent
            final_data_payload = {
                "nodes": output_nodes,
                "relaxed_filters": relaxed_filters_list
            }

            return self.publish_result(
                ToolResult(
                    result_type="semantic_node_search",
                    content=content_message,
                    data=final_data_payload
                )
            )

        except Exception as e:
            logger.exception("Error in handle_kg_find_node")
            return self.publish_error(ToolResult(result_type="error", content=str(e)))
    def handle_kg_describe_node(self, arguments: Dict[str, Any], tool_message: ToolMessage) -> ToolResult:
        try:
            node_id = arguments.get("node_id")
            if not node_id:
                raise ValueError("Missing 'node_id' in arguments.")
            
            filters = arguments.get("filters", None)
            max_edges_value = arguments.get("max_edges", 50)
            max_edges = int(max_edges_value) if max_edges_value is not None else 50

            # Use the updated describe_node function that handles temporal filtering
            from app.assistant.kg_core.kg_tools import describe_node, parse_filters_from_pydantic
            
            # Parse filters if provided
            parsed_filters = None
            if filters:
                parsed_filters = parse_filters_from_pydantic(filters)
            
            # Call the describe_node function with temporal filtering support
            # Convert string node_id to UUID if needed
            if isinstance(node_id, str):
                node_id = uuid.UUID(node_id)
            description = describe_node(node_id, self.session, parsed_filters, max_edges)

            return self.publish_result(
                ToolResult(
                    result_type="node_description",
                    content=f"Description of node '{description['label']}'",
                    data=description
                )
            )

        except Exception as e:
            logger.exception("Error in handle_describe_node")
            return self.publish_error(ToolResult(result_type="error", content=str(e)))

    def handle_kg_short_describe_node(self, arguments: Dict[str, Any], tool_message: ToolMessage) -> ToolResult:
        node_id = arguments.get("node_id")
        if not node_id:
            raise ValueError("Missing 'node_id'.")
        data = short_describe_node(node_id, self.session, k_edges=5)
        return self.publish_result(ToolResult(result_type="node_short_description", content=f"Short description for {data['label']}", data=data))


    def handle_kg_find_edge(self, arguments: Dict[str, Any], tool_message: ToolMessage) -> ToolResult:
        try:
            node_id = arguments.get("node_id")
            if not node_id:
                raise ValueError("Missing 'node_id'.")

            direction = arguments.get("dir", "both")  # 'in', 'out', or 'both'
            k_value = arguments.get("k", 5)
            k = int(k_value) if k_value is not None else 5
            text = (arguments.get("text") or "").strip().lower()
            type_filter = arguments.get("type_filter")  # str or List[str]
            start_time_after = arguments.get("start_time_after")  # ISO string optional
            trivial_types = set(arguments.get("trivial_types", ["has_email"]))
            importance_default_value = arguments.get("importance_default", 0.5)
            importance_default = float(importance_default_value) if importance_default_value is not None else 0.5

            node = self.session.get(Node, node_id)
            if not node:
                raise ValueError(f"Node {node_id} not found.")

            # Normalize type_filter
            if isinstance(type_filter, str):
                type_filter = [type_filter]
            type_filter = set(type_filter) if type_filter else None

            # Base queries
            q_in = self.session.query(Edge).filter(Edge.target_id == node.id)
            q_out = self.session.query(Edge).filter(Edge.source_id == node.id)

            if type_filter:
                q_in = q_in.filter(Edge.relationship_type.in_(type_filter))
                q_out = q_out.filter(Edge.relationship_type.in_(type_filter))

            if start_time_after:
                try:
                    sta = datetime.fromisoformat(start_time_after.replace("Z", "+00:00"))
                    q_in = q_in.filter(or_(Edge.updated_at >= sta, Edge.created_at >= sta))
                    q_out = q_out.filter(or_(Edge.updated_at >= sta, Edge.created_at >= sta))
                except Exception:
                    pass  # ignore bad dates quietly

            q_in = q_in.order_by(desc(Edge.updated_at), desc(Edge.created_at)).limit(max(k * 6, 24))
            q_out = q_out.order_by(desc(Edge.updated_at), desc(Edge.created_at)).limit(max(k * 6, 24))

            edges: List[tuple] = []
            if direction in ("in", "both"):
                edges += [("in", e) for e in q_in.all()]
            if direction in ("out", "both"):
                edges += [("out", e) for e in q_out.all()]

            # Score edges
            scored = []
            for d, e in edges:
                other = e.source_node if d == "in" else e.target_node
                if not other:
                    continue

                # Importance: per-edge attribute > Edge.importance column > default
                edge_imp_val = None
                if e.attributes:
                    edge_imp_val = e.attributes.get("importance")
                    if isinstance(edge_imp_val, str):
                        try:
                            edge_imp_val = float(edge_imp_val)
                        except ValueError:
                            edge_imp_val = None
                if edge_imp_val is None and e.importance is not None:
                    edge_imp_val = e.importance
                imp = float(edge_imp_val) if edge_imp_val is not None else importance_default

                # Recency
                ts = e.updated_at or e.created_at
                rec = _recency_score(ts)

                # Text relevance, cheap heuristic (no embed here)
                txt_score = 0.0
                if text:
                    lbl = (other.label or "").lower()
                    etname = (e.relationship_type or "").lower()
                    aliases = [a.lower() for a in (other.aliases or [])]
                    if text == lbl:
                        txt_score = 1.0
                    elif any(text == a for a in aliases):
                        txt_score = 0.95
                    elif text in lbl:
                        txt_score = 0.8
                    elif any(text in a for a in aliases):
                        txt_score = 0.7
                    elif text in etname:
                        txt_score = 0.6

                # Blend
                score = 0.45 * txt_score + 0.35 * imp + 0.20 * rec

                scored.append({
                    "edge_id": str(e.id),
                    "direction": d,
                    "edge_type": e.relationship_type,
                    "other_node_id": str(other.id),
                    "other_node_label": other.label,
                    "importance": round(float(imp), 4),
                    "updated_at": ts.isoformat() if ts else None,
                    "score": round(float(score), 4),
                    "why": [s for s in [
                        f"importance {imp:.2f}" if imp else None,
                        "recent" if rec > 0.5 else None,
                        f"text≈{txt_score:.2f}" if txt_score > 0 else None
                    ] if s]
                })

            # Sort by score then recency
            scored.sort(key=lambda x: (x["score"], x["updated_at"] or ""), reverse=True)

            # De-dup inverse duplicates and enforce diversity
            seen_pair = set()  # (edge_type, other_node_id)
            seen_per_type: Dict[str, int] = {}
            result = []
            for s in scored:
                pair = (s["edge_type"], s["other_node_id"])
                if pair in seen_pair:
                    continue
                cap = 1 if s["edge_type"] in trivial_types else 2
                if seen_per_type.get(s["edge_type"], 0) >= cap:
                    continue
                result.append(s)
                seen_pair.add(pair)
                seen_per_type[s["edge_type"]] = seen_per_type.get(s["edge_type"], 0) + 1
                if len(result) >= k:
                    break

            return self.publish_result(
                ToolResult(
                    result_type="edge_search",
                    content=f"Top {len(result)} edge(s) for node '{node.label}'",
                    data_list=result
                )
            )

        except Exception as e:
            logger.exception("Error in handle_find_edges")
            return self.publish_error(ToolResult(result_type="error", content=str(e)))



    def handle_kg_describe_edge(self, arguments: Dict[str, Any], tool_message: ToolMessage) -> ToolResult:
        try:
            edge_id = arguments.get("edge_id")
            if not edge_id:
                raise ValueError("Missing 'edge_id' in arguments.")

            # Call your describe function
            data = describe_edge(edge_id=edge_id, session=self.session)

            # Optional perspective to make direction explicit
            perspective_node_id = arguments.get("perspective_node_id")
            if perspective_node_id and data.get("source") and data.get("target"):
                src_id = str(data["source"].get("node_id"))
                tgt_id = str(data["target"].get("node_id"))
                pid = str(perspective_node_id)
                if pid == src_id:
                    data["direction_from_perspective"] = "out"
                elif pid == tgt_id:
                    data["direction_from_perspective"] = "in"
                else:
                    data["direction_from_perspective"] = "none"

            return self.publish_result(
                ToolResult(
                    result_type="edge_description",
                    content=f"Description of edge '{data.get('type', '')}'",
                    data=data,
                )
            )

        except Exception as e:
            logger.exception("Error in handle_describe_edge")
            return self.publish_error(ToolResult(result_type="error", content=str(e)))


if __name__ == "__main__":
    import sys
    from uuid import UUID

    tool = KnowledgeGraphSearch()

    print("\n=== Testing semantic_find_node_by_text ===")
    search_msg = ToolMessage(
        tool_name="kg_find_node",
        tool_data={
            "tool_name": "kg_find_node",
            "arguments": {"text": "Katy", "threshold": 0.75, "k": 3, "edges_k": 3},
        },
    )
    result = tool.execute(search_msg)
    print(result)

    if not result.data_list:
        print("\nNo nodes found in semantic search. Skipping follow-ups.")
        sys.exit(0)

    first_node_id = result.data_list[0]["node_id"]
    try:
        UUID(first_node_id)
    except ValueError:
        print(f"Invalid node_id format: {first_node_id}")
        sys.exit(1)

    # Short describe via handler, not direct function call
    print("\n=== Testing short_describe_node ===")
    short_msg = ToolMessage(
        tool_name="kg_short_describe_node",  # add a handler for this as suggested
        tool_data={
            "tool_name": "kg_short_describe_node",
            "arguments": {"node_id": first_node_id, "k_edges": 5},
        },
    )
    short_res = tool.execute(short_msg)
    print(short_res)

    # Find edges by text from the node
    print("\n=== Testing find_edges (text='work') ===")
    edges_msg = ToolMessage(
        tool_name="kg_find_edges",
        tool_data={
            "tool_name": "kg_find_edges",
            "arguments": {
                "node_id": first_node_id,
                "text": "work",     # try also "email" or "married"
                "dir": "both",
                "k": 5,
                "type_filter": None,   # or ["works_for", "has_email"]
                "start_time_after": None, # or "2024-01-01T00:00:00Z"
            },
        },
    )
    edges_res = tool.execute(edges_msg)
    print(edges_res)

    if edges_res.data_list:
        first_edge_id = edges_res.data_list[0]["edge_id"]

        print(f"\n=== Testing describe_edge ({first_edge_id}) ===")
        edge_msg = ToolMessage(
            tool_name="kg_describe_edge",
            tool_data={
                "tool_name": "kg_describe_edge",
                "arguments": {
                    "edge_id": first_edge_id
                }
            }
        )
        edge_res = tool.execute(edge_msg)
        print(edge_res)
    else:
        print("\nNo edges found to describe.")

    # Clean up
    if tool.session:
        tool.session.close()
