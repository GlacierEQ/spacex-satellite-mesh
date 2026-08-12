//! Deterministic native routing kernel for local satellite-mesh simulation.
//!
//! The crate validates an in-memory undirected graph and computes the
//! lowest-latency route subject to active-node, active-link, residual-capacity,
//! and maximum-latency constraints. It does not control laser terminals or
//! claim production constellation scale.

use std::cmp::Ordering;
use std::collections::{BinaryHeap, HashMap, HashSet};
use std::error::Error;
use std::fmt::{Display, Formatter};

#[derive(Debug, Clone, PartialEq)]
pub struct Node {
    pub id: u32,
    pub active: bool,
    pub load: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Edge {
    pub from: u32,
    pub to: u32,
    pub latency_ms: f64,
    pub capacity_gbps: f64,
    pub current_load_gbps: f64,
    pub active: bool,
}

impl Edge {
    pub fn available_capacity_gbps(&self) -> f64 {
        (self.capacity_gbps - self.current_load_gbps).max(0.0)
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct Route {
    pub path: Vec<u32>,
    pub total_latency_ms: f64,
    pub min_capacity_gbps: f64,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub enum GraphError {
    DuplicateNode(u32),
    UnknownEndpoint(u32),
    DuplicateEdge(u32, u32),
    SelfEdge(u32),
    InvalidNodeLoad(u32),
    InvalidEdge(u32, u32),
    InvalidLatencyLimit,
}

impl Display for GraphError {
    fn fmt(&self, f: &mut Formatter<'_>) -> std::fmt::Result {
        write!(f, "{self:?}")
    }
}

impl Error for GraphError {}

#[derive(Debug, Default, Clone)]
pub struct Graph {
    nodes: HashMap<u32, Node>,
    edges: HashMap<(u32, u32), Edge>,
    adjacency: HashMap<u32, Vec<u32>>,
}

#[derive(Debug, Clone, Copy)]
struct QueueState {
    latency_ms: f64,
    node: u32,
}

impl Eq for QueueState {}

impl PartialEq for QueueState {
    fn eq(&self, other: &Self) -> bool {
        self.node == other.node && self.latency_ms == other.latency_ms
    }
}

impl Ord for QueueState {
    fn cmp(&self, other: &Self) -> Ordering {
        other
            .latency_ms
            .total_cmp(&self.latency_ms)
            .then_with(|| other.node.cmp(&self.node))
    }
}

impl PartialOrd for QueueState {
    fn partial_cmp(&self, other: &Self) -> Option<Ordering> {
        Some(self.cmp(other))
    }
}

impl Graph {
    pub fn add_node(&mut self, node: Node) -> Result<(), GraphError> {
        if !node.load.is_finite() || node.load < 0.0 {
            return Err(GraphError::InvalidNodeLoad(node.id));
        }
        if self.nodes.contains_key(&node.id) {
            return Err(GraphError::DuplicateNode(node.id));
        }
        self.adjacency.entry(node.id).or_default();
        self.nodes.insert(node.id, node);
        Ok(())
    }

    pub fn add_edge(&mut self, edge: Edge) -> Result<(), GraphError> {
        if edge.from == edge.to {
            return Err(GraphError::SelfEdge(edge.from));
        }
        for endpoint in [edge.from, edge.to] {
            if !self.nodes.contains_key(&endpoint) {
                return Err(GraphError::UnknownEndpoint(endpoint));
            }
        }
        if self.edges.contains_key(&(edge.from, edge.to))
            || self.edges.contains_key(&(edge.to, edge.from))
        {
            return Err(GraphError::DuplicateEdge(edge.from, edge.to));
        }
        if !edge.latency_ms.is_finite()
            || edge.latency_ms < 0.0
            || !edge.capacity_gbps.is_finite()
            || edge.capacity_gbps <= 0.0
            || !edge.current_load_gbps.is_finite()
            || edge.current_load_gbps < 0.0
        {
            return Err(GraphError::InvalidEdge(edge.from, edge.to));
        }
        let reverse = Edge {
            from: edge.to,
            to: edge.from,
            latency_ms: edge.latency_ms,
            capacity_gbps: edge.capacity_gbps,
            current_load_gbps: edge.current_load_gbps,
            active: edge.active,
        };
        self.adjacency.entry(edge.from).or_default().push(edge.to);
        self.adjacency.entry(edge.to).or_default().push(edge.from);
        self.adjacency.get_mut(&edge.from).unwrap().sort_unstable();
        self.adjacency.get_mut(&edge.to).unwrap().sort_unstable();
        self.edges.insert((edge.from, edge.to), edge);
        self.edges.insert((reverse.from, reverse.to), reverse);
        Ok(())
    }

    fn usable(&self, from: u32, to: u32) -> bool {
        let Some(source) = self.nodes.get(&from) else {
            return false;
        };
        let Some(destination) = self.nodes.get(&to) else {
            return false;
        };
        let Some(edge) = self.edges.get(&(from, to)) else {
            return false;
        };
        source.active && destination.active && edge.active && edge.available_capacity_gbps() > 0.0
    }

    pub fn route(&self, src: u32, dst: u32, max_latency_ms: f64) -> Result<Option<Route>, GraphError> {
        if !max_latency_ms.is_finite() || max_latency_ms < 0.0 {
            return Err(GraphError::InvalidLatencyLimit);
        }
        let Some(source) = self.nodes.get(&src) else {
            return Ok(None);
        };
        let Some(destination) = self.nodes.get(&dst) else {
            return Ok(None);
        };
        if !source.active || !destination.active {
            return Ok(None);
        }
        if src == dst {
            return Ok(Some(Route {
                path: vec![src],
                total_latency_ms: 0.0,
                min_capacity_gbps: f64::INFINITY,
            }));
        }

        let mut distance: HashMap<u32, f64> = HashMap::from([(src, 0.0)]);
        let mut previous: HashMap<u32, u32> = HashMap::new();
        let mut queue = BinaryHeap::from([QueueState {
            latency_ms: 0.0,
            node: src,
        }]);
        let mut settled = HashSet::new();

        while let Some(state) = queue.pop() {
            if settled.contains(&state.node) {
                continue;
            }
            let known = *distance.get(&state.node).unwrap_or(&f64::INFINITY);
            if state.latency_ms > known {
                continue;
            }
            settled.insert(state.node);
            if state.node == dst {
                break;
            }
            for &neighbor in self.adjacency.get(&state.node).into_iter().flatten() {
                if settled.contains(&neighbor) || !self.usable(state.node, neighbor) {
                    continue;
                }
                let edge = &self.edges[&(state.node, neighbor)];
                let candidate = state.latency_ms + edge.latency_ms;
                if candidate > max_latency_ms {
                    continue;
                }
                if candidate < *distance.get(&neighbor).unwrap_or(&f64::INFINITY) {
                    distance.insert(neighbor, candidate);
                    previous.insert(neighbor, state.node);
                    queue.push(QueueState {
                        latency_ms: candidate,
                        node: neighbor,
                    });
                }
            }
        }

        let Some(&total_latency_ms) = distance.get(&dst) else {
            return Ok(None);
        };
        let mut path = vec![dst];
        while *path.last().unwrap() != src {
            let Some(&parent) = previous.get(path.last().unwrap()) else {
                return Ok(None);
            };
            path.push(parent);
        }
        path.reverse();
        let min_capacity_gbps = path
            .windows(2)
            .map(|pair| self.edges[&(pair[0], pair[1])].available_capacity_gbps())
            .fold(f64::INFINITY, f64::min);
        Ok(Some(Route {
            path,
            total_latency_ms,
            min_capacity_gbps,
        }))
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn node(id: u32) -> Node {
        Node {
            id,
            active: true,
            load: 0.0,
        }
    }

    fn edge(from: u32, to: u32, latency_ms: f64, capacity_gbps: f64) -> Edge {
        Edge {
            from,
            to,
            latency_ms,
            capacity_gbps,
            current_load_gbps: 0.0,
            active: true,
        }
    }

    #[test]
    fn chooses_lowest_latency_viable_route() {
        let mut graph = Graph::default();
        for id in 0..4 {
            graph.add_node(node(id)).unwrap();
        }
        graph.add_edge(edge(0, 1, 5.0, 20.0)).unwrap();
        graph.add_edge(edge(1, 3, 5.0, 20.0)).unwrap();
        graph.add_edge(edge(0, 2, 8.0, 50.0)).unwrap();
        graph.add_edge(edge(2, 3, 8.0, 50.0)).unwrap();
        let route = graph.route(0, 3, 100.0).unwrap().unwrap();
        assert_eq!(route.path, vec![0, 1, 3]);
        assert_eq!(route.total_latency_ms, 10.0);
        assert_eq!(route.min_capacity_gbps, 20.0);
    }

    #[test]
    fn saturated_link_is_not_routable() {
        let mut graph = Graph::default();
        graph.add_node(node(0)).unwrap();
        graph.add_node(node(1)).unwrap();
        let mut link = edge(0, 1, 1.0, 10.0);
        link.current_load_gbps = 10.0;
        graph.add_edge(link).unwrap();
        assert!(graph.route(0, 1, 100.0).unwrap().is_none());
    }

    #[test]
    fn inactive_endpoint_is_not_routable() {
        let mut graph = Graph::default();
        graph.add_node(node(0)).unwrap();
        graph
            .add_node(Node {
                id: 1,
                active: false,
                load: 0.0,
            })
            .unwrap();
        graph.add_edge(edge(0, 1, 1.0, 10.0)).unwrap();
        assert!(graph.route(0, 1, 100.0).unwrap().is_none());
    }

    #[test]
    fn invalid_edges_are_rejected() {
        let mut graph = Graph::default();
        graph.add_node(node(0)).unwrap();
        graph.add_node(node(1)).unwrap();
        let mut bad = edge(0, 1, -1.0, 10.0);
        assert_eq!(graph.add_edge(bad.clone()), Err(GraphError::InvalidEdge(0, 1)));
        bad.latency_ms = 1.0;
        bad.capacity_gbps = 0.0;
        assert_eq!(graph.add_edge(bad), Err(GraphError::InvalidEdge(0, 1)));
    }
}
