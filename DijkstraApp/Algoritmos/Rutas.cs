using DijkstraApp.Modelos;

namespace DijkstraApp.Algoritmos;

/// <summary>Una ruta concreta entre dos nodos con su costo total.</summary>
public record Ruta(IReadOnlyList<Nodo> Nodos, double Costo)
{
    public override string ToString() => string.Join(" → ", Nodos);
}

/// <summary>
/// Enumera por fuerza bruta todas las rutas simples (sin repetir nodos) entre dos nodos.
/// Sirve para comparar alternativas y para validar el resultado de Dijkstra;
/// su costo es exponencial, por eso se limita la cantidad de rutas.
/// </summary>
public static class Rutas
{
    public const int LimitePorDefecto = 200;

    public static List<Ruta> TodasLasRutas(Grafo grafo, Nodo origen, Nodo destino, int limite = LimitePorDefecto)
    {
        var rutas = new List<Ruta>();
        var actual = new List<Nodo> { origen };
        var enRuta = new HashSet<Nodo> { origen };

        void Explorar(Nodo nodo, double costo)
        {
            if (rutas.Count >= limite)
                return;

            if (nodo == destino)
            {
                rutas.Add(new Ruta(actual.ToList(), costo));
                return;
            }

            foreach (var (vecino, peso) in grafo.Vecinos(nodo))
            {
                if (!enRuta.Add(vecino))
                    continue;
                actual.Add(vecino);
                Explorar(vecino, costo + peso);
                actual.RemoveAt(actual.Count - 1);
                enRuta.Remove(vecino);
            }
        }

        Explorar(origen, 0);
        return rutas.OrderBy(r => r.Costo).ThenBy(r => r.Nodos.Count).ToList();
    }

    /// <summary>Suma los pesos de las aristas de un camino (∞ si alguna arista no existe).</summary>
    public static double CostoDe(Grafo grafo, IReadOnlyList<Nodo> camino)
    {
        double total = 0;
        for (var i = 0; i + 1 < camino.Count; i++)
        {
            var arista = grafo.BuscarArista(camino[i], camino[i + 1]);
            if (arista == null)
                return double.PositiveInfinity;
            total += arista.Peso;
        }
        return total;
    }
}
