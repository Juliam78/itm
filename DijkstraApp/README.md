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

1. Al iniciar se carga un grafo de ejemplo (botón **Cargar grafo de ejemplo**).
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

Colores: azul = sin visitar, naranja = nodo actual, verde = visitado,
rojo = camino más corto. Sobre cada nodo se muestra su distancia `d` provisional.

## Estructura

| Archivo | Contenido |
|---|---|
| `Modelos/Grafo.cs` | Clases `Nodo`, `Arista` y `Grafo` (lista de aristas, dirigido o no). |
| `Algoritmos/Dijkstra.cs` | Implementación con `PriorityQueue` – O((V + E) log V) – que guarda cada paso. |
| `MainForm.cs` | Interfaz: lienzo de dibujo, controles, tabla de distancias y registro. |
| `Program.cs` | Punto de entrada. |

## Sobre el algoritmo

Dijkstra encuentra las distancias mínimas desde un nodo origen a todos los demás en
grafos con pesos **no negativos**:

1. `dist[origen] = 0` y `dist[v] = ∞` para el resto.
2. Se toma el nodo no visitado con menor distancia y se marca como visitado.
3. Para cada vecino `v` se *relaja* la arista: si `dist[u] + peso(u,v) < dist[v]`,
   se actualiza `dist[v]` y `previo[v] = u`.
4. Se repite hasta visitar todos los nodos alcanzables. El camino se reconstruye
   siguiendo `previo` desde el destino.
