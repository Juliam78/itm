using DijkstraApp.Modelos;

namespace DijkstraApp.Algoritmos;

/// <summary>Estado del algoritmo en un instante, usado para la ejecución paso a paso.</summary>
public class PasoDijkstra
{
    public Nodo? NodoActual { get; init; }
    public Nodo? VecinoEvaluado { get; init; }
    public IReadOnlyDictionary<Nodo, double> Distancias { get; init; } = new Dictionary<Nodo, double>();
    public IReadOnlyDictionary<Nodo, Nodo?> Previos { get; init; } = new Dictionary<Nodo, Nodo?>();
    public IReadOnlySet<Nodo> Visitados { get; init; } = new HashSet<Nodo>();
    public string Descripcion { get; init; } = "";
}

public class ResultadoDijkstra
{
    public Nodo Origen { get; init; } = null!;
    public Dictionary<Nodo, double> Distancias { get; init; } = new();
    public Dictionary<Nodo, Nodo?> Previos { get; init; } = new();
    public List<PasoDijkstra> Pasos { get; init; } = new();

    /// <summary>Reconstruye el camino más corto hasta el destino (vacío si no es alcanzable).</summary>
    public List<Nodo> CaminoHasta(Nodo destino)
    {
        var camino = new List<Nodo>();
        if (!Distancias.TryGetValue(destino, out var d) || double.IsPositiveInfinity(d))
            return camino;

        for (Nodo? n = destino; n != null; n = Previos[n])
            camino.Add(n);

        camino.Reverse();
        return camino;
    }
}

public static class Dijkstra
{
    /// <summary>
    /// Calcula las distancias mínimas desde <paramref name="origen"/> a todos los nodos.
    /// Usa una cola de prioridad: O((V + E) log V).
    /// </summary>
    public static ResultadoDijkstra Ejecutar(Grafo grafo, Nodo origen)
    {
        var dist = grafo.Nodos.ToDictionary(n => n, _ => double.PositiveInfinity);
        var prev = grafo.Nodos.ToDictionary(n => n, _ => (Nodo?)null);
        var visitados = new HashSet<Nodo>();
        var pasos = new List<PasoDijkstra>();
        var cola = new PriorityQueue<Nodo, double>();

        dist[origen] = 0;
        cola.Enqueue(origen, 0);
        pasos.Add(Capturar(null, null, dist, prev, visitados,
            $"Inicio: distancia({origen}) = 0, el resto = ∞."));

        while (cola.TryDequeue(out var actual, out var prioridad))
        {
            // Entrada obsoleta: ya se encontró una distancia menor antes.
            if (visitados.Contains(actual) || prioridad > dist[actual])
                continue;

            visitados.Add(actual);
            pasos.Add(Capturar(actual, null, dist, prev, visitados,
                $"Se toma {actual} (distancia {Formato(dist[actual])}), el no visitado más cercano."));

            foreach (var (vecino, peso) in grafo.Vecinos(actual))
            {
                if (visitados.Contains(vecino))
                    continue;

                var nueva = dist[actual] + peso;
                string descripcion;
                if (nueva < dist[vecino])
                {
                    descripcion = $"  {actual} → {vecino}: {Formato(dist[actual])} + {Formato(peso)} = {Formato(nueva)} " +
                                  $"< {Formato(dist[vecino])}. Se actualiza.";
                    dist[vecino] = nueva;
                    prev[vecino] = actual;
                    cola.Enqueue(vecino, nueva);
                }
                else
                {
                    descripcion = $"  {actual} → {vecino}: {Formato(dist[actual])} + {Formato(peso)} = {Formato(nueva)} " +
                                  $"≥ {Formato(dist[vecino])}. No mejora.";
                }

                pasos.Add(Capturar(actual, vecino, dist, prev, visitados, descripcion));
            }
        }

        pasos.Add(Capturar(null, null, dist, prev, visitados, "Fin: no quedan nodos por visitar."));

        return new ResultadoDijkstra
        {
            Origen = origen,
            Distancias = dist,
            Previos = prev,
            Pasos = pasos
        };
    }

    public static string Formato(double valor) =>
        double.IsPositiveInfinity(valor) ? "∞" : valor.ToString("0.##");

    private static PasoDijkstra Capturar(Nodo? actual, Nodo? vecino,
        Dictionary<Nodo, double> dist, Dictionary<Nodo, Nodo?> prev, HashSet<Nodo> visitados, string descripcion) =>
        new()
        {
            NodoActual = actual,
            VecinoEvaluado = vecino,
            Distancias = new Dictionary<Nodo, double>(dist),
            Previos = new Dictionary<Nodo, Nodo?>(prev),
            Visitados = new HashSet<Nodo>(visitados),
            Descripcion = descripcion
        };
}
