using System.Drawing;

namespace DijkstraApp.Modelos;

/// <summary>Vértice del grafo, con una posición para dibujarlo en pantalla.</summary>
public class Nodo
{
    public int Id { get; }
    public string Nombre { get; set; }
    public PointF Posicion { get; set; }

    public Nodo(int id, string nombre, PointF posicion)
    {
        Id = id;
        Nombre = nombre;
        Posicion = posicion;
    }

    public override string ToString() => Nombre;
}

/// <summary>Arista ponderada entre dos nodos.</summary>
public class Arista
{
    public Nodo Origen { get; }
    public Nodo Destino { get; }
    public double Peso { get; set; }

    public Arista(Nodo origen, Nodo destino, double peso)
    {
        Origen = origen;
        Destino = destino;
        Peso = peso;
    }

    public bool Conecta(Nodo a, Nodo b) =>
        (Origen == a && Destino == b) || (Origen == b && Destino == a);
}

/// <summary>Grafo ponderado (dirigido o no dirigido).</summary>
public class Grafo
{
    private int _siguienteId;

    public List<Nodo> Nodos { get; } = new();
    public List<Arista> Aristas { get; } = new();
    public bool Dirigido { get; set; }

    public Nodo AgregarNodo(PointF posicion, string? nombre = null)
    {
        var id = _siguienteId++;
        var nodo = new Nodo(id, nombre ?? GenerarNombre(id), posicion);
        Nodos.Add(nodo);
        return nodo;
    }

    /// <summary>Agrega una arista o actualiza el peso si ya existe.</summary>
    public Arista AgregarArista(Nodo origen, Nodo destino, double peso)
    {
        if (peso < 0)
            throw new ArgumentOutOfRangeException(nameof(peso), "Dijkstra no admite pesos negativos.");

        var existente = BuscarArista(origen, destino);
        if (existente != null)
        {
            existente.Peso = peso;
            return existente;
        }

        var arista = new Arista(origen, destino, peso);
        Aristas.Add(arista);
        return arista;
    }

    public Arista? BuscarArista(Nodo origen, Nodo destino) =>
        Dirigido
            ? Aristas.FirstOrDefault(a => a.Origen == origen && a.Destino == destino)
            : Aristas.FirstOrDefault(a => a.Conecta(origen, destino));

    public void EliminarNodo(Nodo nodo)
    {
        Aristas.RemoveAll(a => a.Origen == nodo || a.Destino == nodo);
        Nodos.Remove(nodo);
    }

    public void EliminarArista(Arista arista) => Aristas.Remove(arista);

    /// <summary>Vecinos alcanzables desde un nodo junto con el peso de la arista.</summary>
    public IEnumerable<(Nodo Vecino, double Peso)> Vecinos(Nodo nodo)
    {
        foreach (var a in Aristas)
        {
            if (a.Origen == nodo)
                yield return (a.Destino, a.Peso);
            else if (!Dirigido && a.Destino == nodo)
                yield return (a.Origen, a.Peso);
        }
    }

    public void Limpiar()
    {
        Nodos.Clear();
        Aristas.Clear();
        _siguienteId = 0;
    }

    // A, B, ..., Z, A1, B1, ...
    private static string GenerarNombre(int id)
    {
        var letra = (char)('A' + id % 26);
        var vuelta = id / 26;
        return vuelta == 0 ? letra.ToString() : $"{letra}{vuelta}";
    }
}
