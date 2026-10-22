# DijkstraApp – Algoritmo de Dijkstra en grafos

Aplicación de escritorio básica en **.NET 8 / Windows Forms** para construir un grafo
ponderado y calcular el camino más corto entre dos nodos con el algoritmo de Dijkstra,
mostrando la ejecución paso a paso.

## Requisitos

- Windows
- [.NET 8 SDK](https://dotnet.microsoft.com/download/dotnet/8.0)

## Ejecutar

```bash
cd DijkstraApp
dotnet run
```

También se puede abrir `DijkstraApp.csproj` en Visual Studio 2022 y pulsar F5.

## Uso

1. Al iniciar se carga el **ejemplo de pedido**: 5 rutas del Almacén al Cliente con
   pesos en minutos (botones **Ejemplo: pedido (5 rutas)** y **Ejemplo: grafo clásico**).
2. Modos de edición (panel izquierdo):
   - **Agregar nodo**: clic en un espacio vacío del lienzo.
   - **Agregar arista**: clic en el nodo inicial y luego en el final; usa el valor de
     *Peso de la nueva arista*. Si la arista ya existe, se actualiza su peso.
   - **Mover nodo**: arrastrar un nodo.
   - **Eliminar**: clic sobre un nodo o una arista.
3. Marque **Grafo dirigido** si las aristas tienen sentido.
4. Elija **origen** y **destino** y pulse **Ejecutar Dijkstra**.
5. Use **◀ Paso / Paso ▶** para recorrer la ejecución, o **Ver resultado final**
   para ver el camino más corto resaltado en rojo y su costo.

Al ejecutar, la tabla **Comparación de rutas** lista *todas* las rutas posibles del
origen al destino, de la más rápida a la más lenta, con la diferencia frente a la mejor.
Al hacer clic en una fila, esa ruta se dibuja en azul. El registro confirma con
"✔ Validado" que la ruta de Dijkstra es la más rápida de todas las evaluadas.

Colores: azul = sin visitar, naranja = nodo actual, verde = visitado,
rojo = camino más corto. Sobre cada nodo se muestra su distancia `d` provisional.

## Estructura

| Archivo | Contenido |
|---|---|
| `Modelos/Ejemplos.cs` | Grafos de ejemplo: pedido con 5 rutas y grafo clásico. |
| `Algoritmos/Rutas.cs` | Enumera todas las rutas posibles (fuerza bruta) para compararlas. |
| `Modelos/Grafo.cs` | Clases `Nodo`, `Arista` y `Grafo` (lista de aristas, dirigido o no). |
| `Algoritmos/Dijkstra.cs` | Implementación con `PriorityQueue` – O((V + E) log V) – que guarda cada paso. |
| `MainForm.cs` | Interfaz: lienzo de dibujo, controles, tabla de distancias y registro. |
| `Program.cs` | Punto de entrada. |

## Validación

El proyecto de consola `DijkstraApp.Validacion` (corre en Windows, Linux o macOS)
comprueba el algoritmo:

```bash
cd DijkstraApp.Validacion
dotnet run
```

1. **Pedido con 5 rutas**: Dijkstra debe elegir la ruta por la Autopista (18 min), que
   coincide con la mejor de las 5; y si la autopista se congestiona (5 → 15 min) debe
   cambiar a Barrio Sur (21 min).
2. **Casos borde**: origen = destino, nodo aislado, sentido único y pesos negativos.
3. **1000 grafos aleatorios** (dirigidos y no dirigidos): la distancia de Dijkstra a cada
   nodo debe ser igual al costo de la mejor ruta encontrada probando *todas* las rutas.

Termina con `✔ VALIDACIÓN EXITOSA` (código de salida 0) o lista los fallos (código 1).

### Para usarlo con sus propias rutas

Cada nodo es un punto (almacén, cruce, cliente) y cada arista un tramo, con su
tiempo como peso. Use siempre la misma unidad (minutos, por ejemplo) y no use pesos
negativos. Si un tramo es de un solo sentido, marque **Grafo dirigido**.

## Sobre el algoritmo

Dijkstra encuentra las distancias mínimas desde un nodo origen a todos los demás en
grafos con pesos **no negativos**:

1. `dist[origen] = 0` y `dist[v] = ∞` para el resto.
2. Se toma el nodo no visitado con menor distancia y se marca como visitado.
3. Para cada vecino `v` se *relaja* la arista: si `dist[u] + peso(u,v) < dist[v]`,
   se actualiza `dist[v]` y `previo[v] = u`.
4. Se repite hasta visitar todos los nodos alcanzables. El camino se reconstruye
   siguiendo `previo` desde el destino.
