import networkx as nx
from database.models import TaskModel, PipelineModel
from src.utils.logger import get_logger

logger = get_logger("Scheduler")


class DAGScheduler:
    """
    DAG Job Engine powered by NetworkX.
    Manages dependency graphs, topological order, ready-state resolution, and failure cascades.
    """

    @classmethod
    def build_graph(cls, pipeline_id: str) -> nx.DiGraph:
        """
        Builds a NetworkX Directed Acyclic Graph (DiGraph) from database tasks.
        Nodes represent EDA stages (Synthesis, Floorplan, etc.).
        Directed edges represent execution dependencies (Parent -> Child).
        """
        tasks = TaskModel.get_by_pipeline(pipeline_id)
        G = nx.DiGraph()

        # 1. Add all tasks as nodes
        for task in tasks:
            task_dict = dict(task)
            G.add_node(task_dict["id"], **task_dict)

        # 2. Add dependency edges: parent -> child
        for task in tasks:
            task_dict = dict(task)
            deps = task_dict.get("dependencies", "")
            if deps:
                parent_ids = [d.strip() for d in deps.split(",") if d.strip()]
                for parent_id in parent_ids:
                    if G.has_node(parent_id):
                        G.add_edge(parent_id, task_dict["id"])
                    else:
                        logger.warning(
                            f"Task '{task_dict['id']}' specifies non-existent parent dependency '{parent_id}'"
                        )

        # 3. Validate DAG (Detect circular dependencies)
        if not nx.is_directed_acyclic_graph(G):
            cycles = list(nx.simple_cycles(G))
            raise ValueError(f"Cycle detected in pipeline '{pipeline_id}': {cycles}")

        return G

    @classmethod
    def get_ready_tasks(cls, pipeline_id: str) -> list:
        """
        Returns all tasks that are currently runnable:
        - Task status is 'PENDING'
        - All parent predecessor tasks have completed successfully ('COMPLETED')
        """
        G = cls.build_graph(pipeline_id)
        ready_tasks = []

        for node_id in G.nodes():
            node_data = G.nodes[node_id]
            if node_data["status"] != "PENDING":
                continue

            # Check all parent dependencies
            predecessors = list(G.predecessors(node_id))
            all_parents_done = True
            for parent_id in predecessors:
                parent_status = G.nodes[parent_id]["status"]
                if parent_status != "COMPLETED":
                    all_parents_done = False
                    break

            if all_parents_done:
                ready_tasks.append(node_data)

        return ready_tasks

    @classmethod
    def handle_failed_task(cls, pipeline_id: str, failed_task_id: str):
        """
        Cascades failure downstream: if an EDA stage fails (e.g. Synthesis error),
        all downstream dependent stages (Placement, CTS, Routing) are marked 'SKIPPED'.
        """
        G = cls.build_graph(pipeline_id)
        if not G.has_node(failed_task_id):
            return

        # Find all downstream dependent nodes in the DAG
        descendants = nx.descendants(G, failed_task_id)
        logger.warning(
            f"Task '{failed_task_id}' failed. Cascading SKIPPED status to {len(descendants)} downstream tasks."
        )

        for child_id in descendants:
            child_status = G.nodes[child_id]["status"]
            if child_status in ("PENDING", "QUEUED"):
                TaskModel.update_status(child_id, "SKIPPED")
                logger.info(f"Task '{child_id}' marked as SKIPPED due to parent failure.")

    @classmethod
    def check_pipeline_completion(cls, pipeline_id: str) -> tuple:
        """
        Evaluates whether all tasks in the pipeline have completed.
        Returns: (is_finished: bool, final_status: str)
        """
        tasks = TaskModel.get_by_pipeline(pipeline_id)
        if not tasks:
            return False, "PENDING"

        terminal_statuses = {"COMPLETED", "FAILED", "SKIPPED"}
        all_terminal = True
        any_failed = False

        for task in tasks:
            status = task["status"]
            if status not in terminal_statuses:
                all_terminal = False
            if status in ("FAILED", "SKIPPED"):
                any_failed = True

        if all_terminal:
            final_status = "FAILED" if any_failed else "COMPLETED"
            PipelineModel.update_status(pipeline_id, final_status)
            return True, final_status

        return False, "RUNNING"

    @classmethod
    def get_dag_for_cytoscape(cls, pipeline_id: str) -> dict:
        """
        Serializes the DAG into Cytoscape.js format for the web dashboard visualization.
        """
        G = cls.build_graph(pipeline_id)
        elements = {"nodes": [], "edges": []}

        for node_id in G.nodes():
            data = G.nodes[node_id]
            elements["nodes"].append({
                "data": {
                    "id": node_id,
                    "name": data.get("name", node_id),
                    "status": data.get("status", "PENDING"),
                    "dependencies": data.get("dependencies", "")
                }
            })

        for u, v in G.edges():
            elements["edges"].append({
                "data": {
                    "id": f"{u}->{v}",
                    "source": u,
                    "target": v
                }
            })

        return elements
