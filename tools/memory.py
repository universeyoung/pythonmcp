import json
import os
import pathlib
from typing import Sequence

from mcp.types import Tool, TextContent, ImageContent, EmbeddedResource
from pydantic import BaseModel, Field


class Entity(BaseModel):
    name: str = Field(description="The name of the entity")
    entityType: str = Field(description="The type of the entity")
    observations: list[str] = Field(description="An array of observation contents associated with the entity")


class Relation(BaseModel):
    from_: str = Field(alias="from", description="The name of the entity where the relation starts")
    to: str = Field(description="The name of the entity where the relation ends")
    relationType: str = Field(description="The type of the relation")


class KnowledgeGraph(BaseModel):
    entities: list[Entity] = Field(default_factory=list)
    relations: list[Relation] = Field(default_factory=list)


class CreateEntitiesInput(BaseModel):
    entities: list[Entity] = Field(description="Array of entities to create")


class CreateRelationsInput(BaseModel):
    relations: list[Relation] = Field(description="Array of relations to create")


class AddObservationsInput(BaseModel):
    observations: list[dict] = Field(description="Array of {entityName, contents} to add")


class DeleteEntitiesInput(BaseModel):
    entityNames: list[str] = Field(description="Array of entity names to delete")


class DeleteObservationsInput(BaseModel):
    deletions: list[dict] = Field(description="Array of {entityName, observations} to delete")


class DeleteRelationsInput(BaseModel):
    relations: list[Relation] = Field(description="Array of relations to delete")


class SearchNodesInput(BaseModel):
    query: str = Field(description="Search query to match against entity names, types, and observations")


class OpenNodesInput(BaseModel):
    names: list[str] = Field(description="Array of entity names to retrieve")


class KnowledgeGraphManager:
    def __init__(self, file_path: str):
        self._file_path = pathlib.Path(file_path)

    def _load_graph(self) -> KnowledgeGraph:
        if not self._file_path.exists():
            return KnowledgeGraph()
        graph = KnowledgeGraph()
        with open(self._file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                item = json.loads(line)
                if item.get("type") == "entity":
                    graph.entities.append(
                        Entity(name=item["name"], entityType=item["entityType"], observations=item.get("observations", []))
                    )
                elif item.get("type") == "relation":
                    graph.relations.append(
                        Relation(from_=item["from"], to=item["to"], relationType=item["relationType"])
                    )
        return graph

    def _save_graph(self, graph: KnowledgeGraph):
        lines = []
        for e in graph.entities:
            lines.append(
                json.dumps({"type": "entity", "name": e.name, "entityType": e.entityType, "observations": e.observations})
            )
        for r in graph.relations:
            lines.append(
                json.dumps({"type": "relation", "from": r.from_, "to": r.to, "relationType": r.relationType})
            )
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self._file_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

    def create_entities(self, entities: list[Entity]) -> list[Entity]:
        graph = self._load_graph()
        existing_names = {e.name for e in graph.entities}
        new_entities = [e for e in entities if e.name not in existing_names]
        graph.entities.extend(new_entities)
        self._save_graph(graph)
        return new_entities

    def create_relations(self, relations: list[Relation]) -> list[Relation]:
        graph = self._load_graph()
        existing = {(r.from_, r.to, r.relationType) for r in graph.relations}
        new_relations = [r for r in relations if (r.from_, r.to, r.relationType) not in existing]
        graph.relations.extend(new_relations)
        self._save_graph(graph)
        return new_relations

    def add_observations(self, observations: list[dict]) -> list[dict]:
        graph = self._load_graph()
        results = []
        for obs in observations:
            entity = next((e for e in graph.entities if e.name == obs["entityName"]), None)
            if entity is None:
                raise ValueError(f"Entity with name {obs['entityName']} not found")
            new_obs = [c for c in obs["contents"] if c not in entity.observations]
            entity.observations.extend(new_obs)
            results.append({"entityName": obs["entityName"], "addedObservations": new_obs})
        self._save_graph(graph)
        return results

    def delete_entities(self, entity_names: list[str]):
        graph = self._load_graph()
        graph.entities = [e for e in graph.entities if e.name not in entity_names]
        graph.relations = [r for r in graph.relations if r.from_ not in entity_names and r.to not in entity_names]
        self._save_graph(graph)

    def delete_observations(self, deletions: list[dict]):
        graph = self._load_graph()
        for d in deletions:
            entity = next((e for e in graph.entities if e.name == d["entityName"]), None)
            if entity:
                entity.observations = [o for o in entity.observations if o not in d["observations"]]
        self._save_graph(graph)

    def delete_relations(self, relations: list[Relation]):
        graph = self._load_graph()
        to_delete = {(r.from_, r.to, r.relationType) for r in relations}
        graph.relations = [r for r in graph.relations if (r.from_, r.to, r.relationType) not in to_delete]
        self._save_graph(graph)

    def read_graph(self) -> KnowledgeGraph:
        return self._load_graph()

    def search_nodes(self, query: str) -> KnowledgeGraph:
        graph = self._load_graph()
        q = query.lower()
        filtered_entities = [
            e
            for e in graph.entities
            if q in e.name.lower() or q in e.entityType.lower() or any(q in o.lower() for o in e.observations)
        ]
        filtered_names = {e.name for e in filtered_entities}
        filtered_relations = [r for r in graph.relations if r.from_ in filtered_names or r.to in filtered_names]
        return KnowledgeGraph(entities=filtered_entities, relations=filtered_relations)

    def open_nodes(self, names: list[str]) -> KnowledgeGraph:
        graph = self._load_graph()
        filtered_entities = [e for e in graph.entities if e.name in names]
        filtered_names = {e.name for e in filtered_entities}
        filtered_relations = [r for r in graph.relations if r.from_ in filtered_names or r.to in filtered_names]
        return KnowledgeGraph(entities=filtered_entities, relations=filtered_relations)


def _get_memory_file_path() -> str:
    custom = os.environ.get("MEMORY_FILE_PATH", "")
    if custom:
        return custom
    return str(pathlib.Path.home() / ".mcp-memory.jsonl")


_knowledge_graph_manager: KnowledgeGraphManager | None = None


def _get_manager() -> KnowledgeGraphManager:
    global _knowledge_graph_manager
    if _knowledge_graph_manager is None:
        _knowledge_graph_manager = KnowledgeGraphManager(_get_memory_file_path())
    return _knowledge_graph_manager


def get_tools() -> list[Tool]:
    return [
        Tool(
            name="create_entities",
            description="Create multiple new entities in the knowledge graph",
            inputSchema=CreateEntitiesInput.model_json_schema(),
        ),
        Tool(
            name="create_relations",
            description="Create multiple new relations between entities in the knowledge graph. Relations should be in active voice.",
            inputSchema=CreateRelationsInput.model_json_schema(),
        ),
        Tool(
            name="add_observations",
            description="Add new observations to existing entities in the knowledge graph",
            inputSchema=AddObservationsInput.model_json_schema(),
        ),
        Tool(
            name="delete_entities",
            description="Delete multiple entities and their associated relations from the knowledge graph",
            inputSchema=DeleteEntitiesInput.model_json_schema(),
        ),
        Tool(
            name="delete_observations",
            description="Delete specific observations from entities in the knowledge graph",
            inputSchema=DeleteObservationsInput.model_json_schema(),
        ),
        Tool(
            name="delete_relations",
            description="Delete multiple relations from the knowledge graph",
            inputSchema=DeleteRelationsInput.model_json_schema(),
        ),
        Tool(
            name="read_graph",
            description="Read the entire knowledge graph",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="search_nodes",
            description="Search for nodes in the knowledge graph based on a query",
            inputSchema=SearchNodesInput.model_json_schema(),
        ),
        Tool(
            name="open_nodes",
            description="Open specific nodes in the knowledge graph by their names",
            inputSchema=OpenNodesInput.model_json_schema(),
        ),
    ]


async def handle_tool(name: str, arguments: dict) -> Sequence[TextContent | ImageContent | EmbeddedResource] | None:
    mgr = _get_manager()

    match name:
        case "create_entities":
            args = CreateEntitiesInput(**arguments)
            result = mgr.create_entities(args.entities)
            return [TextContent(type="text", text=json.dumps([r.model_dump() for r in result], indent=2))]

        case "create_relations":
            args = CreateRelationsInput(**arguments)
            result = mgr.create_relations(args.relations)
            return [TextContent(type="text", text=json.dumps([r.model_dump(by_alias=True) for r in result], indent=2))]

        case "add_observations":
            args = AddObservationsInput(**arguments)
            result = mgr.add_observations(args.observations)
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        case "delete_entities":
            args = DeleteEntitiesInput(**arguments)
            mgr.delete_entities(args.entityNames)
            return [TextContent(type="text", text="Entities deleted successfully")]

        case "delete_observations":
            args = DeleteObservationsInput(**arguments)
            mgr.delete_observations(args.deletions)
            return [TextContent(type="text", text="Observations deleted successfully")]

        case "delete_relations":
            args = DeleteRelationsInput(**arguments)
            mgr.delete_relations(args.relations)
            return [TextContent(type="text", text="Relations deleted successfully")]

        case "read_graph":
            graph = mgr.read_graph()
            data = {
                "entities": [e.model_dump() for e in graph.entities],
                "relations": [r.model_dump(by_alias=True) for r in graph.relations],
            }
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        case "search_nodes":
            args = SearchNodesInput(**arguments)
            graph = mgr.search_nodes(args.query)
            data = {
                "entities": [e.model_dump() for e in graph.entities],
                "relations": [r.model_dump(by_alias=True) for r in graph.relations],
            }
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        case "open_nodes":
            args = OpenNodesInput(**arguments)
            graph = mgr.open_nodes(args.names)
            data = {
                "entities": [e.model_dump() for e in graph.entities],
                "relations": [r.model_dump(by_alias=True) for r in graph.relations],
            }
            return [TextContent(type="text", text=json.dumps(data, indent=2))]

        case _:
            return None