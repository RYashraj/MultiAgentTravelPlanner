import inspect

START = "__start__"
END = "__end__"

class StateGraph:
    """
    Pure Python minimal compatibility wrapper for langgraph.graph.StateGraph.
    Avoids native binary .pyd imports like xxhash which are blocked by Windows App Control.
    """
    def __init__(self, schema):
        self.schema = schema
        self.nodes = {}
        self.edges = []
        self.entry_point = None
        self.finish_point = None

    def add_node(self, name, func):
        self.nodes[name] = func
        return self

    def set_entry_point(self, name):
        self.entry_point = name
        return self

    def set_finish_point(self, name):
        self.finish_point = name
        return self

    def add_edge(self, start, end):
        self.edges.append((start, end))
        if start == START:
            self.entry_point = end
        if end == END:
            self.finish_point = start
        return self

    def compile(self):
        return CompiledGraph(self)


class CompiledGraph:
    def __init__(self, graph):
        self.graph = graph

    def invoke(self, state, config=None):
        current_state = dict(state)
        curr = self.graph.entry_point
        visited = set()
        
        while curr and curr != END and curr not in visited:
            visited.add(curr)
            func = self.graph.nodes.get(curr)
            if func:
                res = func(current_state)
                if res:
                    for k, v in res.items():
                        current_state[k] = v
            # Find next edge
            next_node = None
            for start, end in self.graph.edges:
                if start == curr:
                    next_node = end
                    break
            curr = next_node
            
        return current_state

    async def ainvoke(self, state, config=None):
        current_state = dict(state)
        curr = self.graph.entry_point
        visited = set()
        
        while curr and curr != END and curr not in visited:
            visited.add(curr)
            func = self.graph.nodes.get(curr)
            if func:
                if inspect.iscoroutinefunction(func):
                    res = await func(current_state)
                else:
                    res = func(current_state)
                if res:
                    for k, v in res.items():
                        current_state[k] = v
            # Find next edge
            next_node = None
            for start, end in self.graph.edges:
                if start == curr:
                    next_node = end
                    break
            curr = next_node
            
        return current_state
