using System.Drawing;

namespace DijkstraApp.Modelos;

/// <summary>Grafos de ejemplo usados por la aplicación y por el programa de validación.</summary>
public static class Ejemplos
{
    /// <summary>Grafo clásico de 6 nodos (A-F).</summary>
    public static void Clasico(Grafo grafo)
    {
        grafo.Limpiar();
        grafo.Dirigido = false;

        var a = grafo.AgregarNodo(new PointF(80, 250));
        var b = grafo.AgregarNodo(new PointF(230, 100));
        var c = grafo.AgregarNodo(new PointF(230, 400));
        var d = grafo.AgregarNodo(new PointF(420, 100));
        var e = grafo.AgregarNodo(new PointF(420, 400));
        var f = grafo.AgregarNodo(new PointF(570, 250));

        grafo.AgregarArista(a, b, 4);
        grafo.AgregarArista(a, c, 2);
        grafo.AgregarArista(b, c, 1);
        grafo.AgregarArista(b, d, 5);
        grafo.AgregarArista(c, d, 8);
        grafo.AgregarArista(c, e, 10);
        grafo.AgregarArista(d, e, 2);
        grafo.AgregarArista(d, f, 6);
        grafo.AgregarArista(e, f, 3);
    }

    /// <summary>
    /// Entrega de un pedido: 5 rutas posibles del Almacén al Cliente.
    /// Los pesos son minutos de recorrido. La más rápida es la ruta 3 (Autopista), 18 min.
    /// </summary>
    public static void Pedido(Grafo grafo)
    {
        grafo.Limpiar();
        grafo.Dirigido = false;

        var almacen = grafo.AgregarNodo(new PointF(90, 300), "Almacén");
        var cliente = grafo.AgregarNodo(new PointF(750, 300), "Cliente");

        // Ruta 1: Av. Principal (10 + 15 = 25 min)
        var principal = grafo.AgregarNodo(new PointF(420, 80), "Av. Principal");
        grafo.AgregarArista(almacen, principal, 10);
        grafo.AgregarArista(principal, cliente, 15);

        // Ruta 2: Centro (8 + 20 = 28 min, menos distancia al inicio pero tráfico en el centro)
        var centro = grafo.AgregarNodo(new PointF(420, 190), "Centro");
        grafo.AgregarArista(almacen, centro, 8);
        grafo.AgregarArista(centro, cliente, 20);

        // Ruta 3: Autopista + Salida Norte (5 + 7 + 6 = 18 min) -> la más rápida
        var autopista = grafo.AgregarNodo(new PointF(310, 300), "Autopista");
        var salida = grafo.AgregarNodo(new PointF(530, 300), "Salida Norte");
        grafo.AgregarArista(almacen, autopista, 5);
        grafo.AgregarArista(autopista, salida, 7);
        grafo.AgregarArista(salida, cliente, 6);

        // Ruta 4: Barrio Sur (12 + 9 = 21 min)
        var sur = grafo.AgregarNodo(new PointF(420, 410), "Barrio Sur");
        grafo.AgregarArista(almacen, sur, 12);
        grafo.AgregarArista(sur, cliente, 9);

        // Ruta 5: Puente (14 + 16 = 30 min)
        var puente = grafo.AgregarNodo(new PointF(420, 520), "Puente");
        grafo.AgregarArista(almacen, puente, 14);
        grafo.AgregarArista(puente, cliente, 16);
    }
}
