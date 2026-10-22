using System.Drawing;
using DijkstraApp.Algoritmos;
using DijkstraApp.Modelos;

// Valida que Dijkstra elige siempre la ruta más rápida, comparándolo con la
// enumeración de TODAS las rutas posibles (fuerza bruta).
var fallos = 0;
var pruebas = 0;

void Verificar(bool condicion, string descripcion)
{
    pruebas++;
    if (condicion) return;
    fallos++;
    Console.WriteLine($"  ✘ FALLO: {descripcion}");
}

static bool Igual(double a, double b) =>
    double.IsPositiveInfinity(a) && double.IsPositiveInfinity(b) || Math.Abs(a - b) < 1e-9;

// ------------------------------------------------------------------ 1. Escenario de pedido
Console.WriteLine("1) Pedido: 5 rutas del Almacén al Cliente (pesos en minutos)");
var pedido = new Grafo();
Ejemplos.Pedido(pedido);
var almacen = pedido.Nodos.Single(n => n.Nombre == "Almacén");
var cliente = pedido.Nodos.Single(n => n.Nombre == "Cliente");

var rutas = Rutas.TodasLasRutas(pedido, almacen, cliente);
for (var i = 0; i < rutas.Count; i++)
    Console.WriteLine($"   {i + 1}. {rutas[i].Costo,3} min  {rutas[i]}");

var resultado = Dijkstra.Ejecutar(pedido, almacen);
var elegido = resultado.CaminoHasta(cliente);
Console.WriteLine($"   Dijkstra elige: {string.Join(" → ", elegido)} ({Dijkstra.Formato(resultado.Distancias[cliente])} min)");

Verificar(rutas.Count == 5, $"se esperaban 5 rutas y hay {rutas.Count}");
Verificar(Igual(resultado.Distancias[cliente], 18), "la ruta más rápida debe ser de 18 min");
Verificar(string.Join(",", elegido) == "Almacén,Autopista,Salida Norte,Cliente", "la ruta elegida debe ser la de la Autopista");
Verificar(Igual(resultado.Distancias[cliente], rutas[0].Costo), "Dijkstra debe coincidir con la mejor ruta enumerada");
Verificar(Igual(Rutas.CostoDe(pedido, elegido), resultado.Distancias[cliente]), "el costo del camino debe sumar sus aristas");

// Si se congestiona la autopista (5 → 15 min), la mejor pasa a ser Barrio Sur (21 min).
var autopista = pedido.Nodos.Single(n => n.Nombre == "Autopista");
pedido.AgregarArista(almacen, autopista, 15);
var conTrafico = Dijkstra.Ejecutar(pedido, almacen);
Console.WriteLine($"   Con tráfico en la autopista: {string.Join(" → ", conTrafico.CaminoHasta(cliente))} " +
                  $"({Dijkstra.Formato(conTrafico.Distancias[cliente])} min)");
Verificar(Igual(conTrafico.Distancias[cliente], 21), "con tráfico la mejor debe ser de 21 min");
Verificar(conTrafico.CaminoHasta(cliente).Any(n => n.Nombre == "Barrio Sur"), "con tráfico debe ir por Barrio Sur");

// ------------------------------------------------------------------ 2. Casos borde
Console.WriteLine("2) Casos borde");
var borde = new Grafo();
var x = borde.AgregarNodo(PointF.Empty);
var y = borde.AgregarNodo(PointF.Empty);
var aislado = borde.AgregarNodo(PointF.Empty);
borde.AgregarArista(x, y, 4);
var rb = Dijkstra.Ejecutar(borde, x);
Verificar(Igual(rb.Distancias[x], 0) && rb.CaminoHasta(x).Count == 1, "origen = destino cuesta 0");
Verificar(double.IsPositiveInfinity(rb.Distancias[aislado]) && rb.CaminoHasta(aislado).Count == 0, "nodo aislado es inalcanzable");
borde.Dirigido = true;
Verificar(double.IsPositiveInfinity(Dijkstra.Ejecutar(borde, y).Distancias[x]), "en dirigido no se puede volver por una arista de un solo sentido");
Verificar(RechazaNegativo(), "pesos negativos se rechazan");
Console.WriteLine("   listo");

static bool RechazaNegativo()
{
    var g = new Grafo();
    try { g.AgregarArista(g.AgregarNodo(PointF.Empty), g.AgregarNodo(PointF.Empty), -1); return false; }
    catch (ArgumentOutOfRangeException) { return true; }
}

// ------------------------------------------------------------------ 3. Grafos aleatorios vs. fuerza bruta
const int cantidad = 1000;
Console.WriteLine($"3) {cantidad} grafos aleatorios: Dijkstra vs. todas las rutas posibles");
var azar = new Random(12345);
for (var caso = 0; caso < cantidad; caso++)
{
    var g = new Grafo { Dirigido = caso % 2 == 1 };
    var n = azar.Next(2, 8);
    for (var i = 0; i < n; i++) g.AgregarNodo(PointF.Empty);
    foreach (var a in g.Nodos)
        foreach (var b in g.Nodos)
            if (a != b && azar.NextDouble() < 0.4)
                g.AgregarArista(a, b, azar.Next(0, 20));

    var origen = g.Nodos[0];
    var r = Dijkstra.Ejecutar(g, origen);
    foreach (var destino in g.Nodos)
    {
        var todas = Rutas.TodasLasRutas(g, origen, destino, int.MaxValue);
        var mejor = todas.Count == 0 ? double.PositiveInfinity : todas[0].Costo;
        var camino = r.CaminoHasta(destino);
        Verificar(Igual(r.Distancias[destino], mejor),
            $"caso {caso}: distancia a {destino} = {r.Distancias[destino]}, la mejor ruta cuesta {mejor}");
        if (camino.Count > 0)
            Verificar(camino[0] == origen && camino[^1] == destino && Igual(Rutas.CostoDe(g, camino), mejor),
                $"caso {caso}: el camino a {destino} no es válido o no cuesta lo mínimo");
    }
}
Console.WriteLine("   listo");

Console.WriteLine();
Console.WriteLine(fallos == 0
    ? $"✔ VALIDACIÓN EXITOSA: {pruebas} comprobaciones correctas."
    : $"✘ {fallos} de {pruebas} comprobaciones fallaron.");
return fallos == 0 ? 0 : 1;
