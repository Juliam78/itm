using System.Drawing.Drawing2D;
using DijkstraApp.Algoritmos;
using DijkstraApp.Modelos;

namespace DijkstraApp;

public class MainForm : Form
{
    private enum Modo { AgregarNodo, AgregarArista, Mover, Eliminar }

    private const float Radio = 20f;

    private readonly Grafo _grafo = new();
    private Modo _modo = Modo.AgregarNodo;
    private Nodo? _nodoSeleccionado;   // primer nodo elegido al crear una arista
    private Nodo? _nodoArrastrado;
    private ResultadoDijkstra? _resultado;
    private int _indicePaso = -1;      // -1 = mostrar el resultado final

    private readonly PanelDibujo _lienzo = new();
    private readonly NumericUpDown _peso = new();
    private readonly CheckBox _dirigido = new();
    private readonly ComboBox _origen = new();
    private readonly ComboBox _destino = new();
    private readonly Button _anterior = new();
    private readonly Button _siguiente = new();
    private readonly ListView _tabla = new();
    private readonly ListView _rutas = new();
    private List<Ruta> _rutasEncontradas = new();
    private Ruta? _rutaSeleccionada;   // ruta alternativa elegida en la tabla de comparación
    private readonly TextBox _registro = new();
    private readonly ToolStripStatusLabel _estado = new();

    public MainForm()
    {
        Text = "Algoritmo de Dijkstra - Camino más corto en grafos";
        Size = new Size(1400, 820);
        MinimumSize = new Size(900, 550);
        StartPosition = FormStartPosition.CenterScreen;
        Font = new Font("Segoe UI", 9f);

        ConstruirInterfaz();
        CargarEjemplo(Ejemplos.Pedido, "Almacén", "Cliente");
    }

    // ------------------------------------------------------------------ Interfaz

    private void ConstruirInterfaz()
    {
        var izquierda = new FlowLayoutPanel
        {
            Dock = DockStyle.Left,
            Width = 230,
            FlowDirection = FlowDirection.TopDown,
            WrapContents = false,
            AutoScroll = true,
            Padding = new Padding(10)
        };

        var grupoModo = new GroupBox { Text = "Modo de edición", Width = 200, Height = 130 };
        var modos = new (string Texto, Modo Modo)[]
        {
            ("Agregar nodo", Modo.AgregarNodo),
            ("Agregar arista", Modo.AgregarArista),
            ("Mover nodo", Modo.Mover),
            ("Eliminar", Modo.Eliminar)
        };
        for (var i = 0; i < modos.Length; i++)
        {
            var (texto, modo) = modos[i];
            var radio = new RadioButton
            {
                Text = texto,
                Location = new Point(12, 22 + i * 25),
                AutoSize = true,
                Checked = i == 0
            };
            radio.CheckedChanged += (_, _) =>
            {
                if (!radio.Checked) return;
                _modo = modo;
                _nodoSeleccionado = null;
                ActualizarAyuda();
                _lienzo.Invalidate();
            };
            grupoModo.Controls.Add(radio);
        }
        izquierda.Controls.Add(grupoModo);

        izquierda.Controls.Add(new Label { Text = "Peso de la nueva arista:", AutoSize = true, Margin = new Padding(3, 10, 3, 3) });
        _peso.Width = 200;
        _peso.Minimum = 0;
        _peso.Maximum = 10000;
        _peso.DecimalPlaces = 1;
        _peso.Value = 1;
        izquierda.Controls.Add(_peso);

        _dirigido.Text = "Grafo dirigido";
        _dirigido.AutoSize = true;
        _dirigido.Margin = new Padding(3, 10, 3, 3);
        _dirigido.CheckedChanged += (_, _) =>
        {
            _grafo.Dirigido = _dirigido.Checked;
            GrafoModificado();
        };
        izquierda.Controls.Add(_dirigido);

        izquierda.Controls.Add(new Label { Text = "Nodo origen:", AutoSize = true, Margin = new Padding(3, 15, 3, 3) });
        _origen.Width = 200;
        _origen.DropDownStyle = ComboBoxStyle.DropDownList;
        _origen.SelectedIndexChanged += (_, _) => InvalidarResultado();
        izquierda.Controls.Add(_origen);

        izquierda.Controls.Add(new Label { Text = "Nodo destino:", AutoSize = true });
        _destino.Width = 200;
        _destino.DropDownStyle = ComboBoxStyle.DropDownList;
        _destino.SelectedIndexChanged += (_, _) => { CalcularRutas(); MostrarResultado(); };
        izquierda.Controls.Add(_destino);

        izquierda.Controls.Add(CrearBoton("Ejecutar Dijkstra", (_, _) => EjecutarDijkstra(), negrita: true));

        // Dos columnas iguales para que ambos botones siempre quepan en el ancho del panel.
        var navegacion = new TableLayoutPanel { Width = 206, Height = 38, ColumnCount = 2, RowCount = 1, Margin = new Padding(0) };
        navegacion.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
        navegacion.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 50f));
        _anterior.Text = "◀ Paso";
        _anterior.Dock = DockStyle.Fill;
        _anterior.Click += (_, _) => MoverPaso(-1);
        _siguiente.Text = "Paso ▶";
        _siguiente.Dock = DockStyle.Fill;
        _siguiente.Click += (_, _) => MoverPaso(+1);
        navegacion.Controls.Add(_anterior, 0, 0);
        navegacion.Controls.Add(_siguiente, 1, 0);
        izquierda.Controls.Add(navegacion);
        izquierda.Controls.Add(CrearBoton("Ver resultado final", (_, _) => { _indicePaso = -1; MostrarResultado(); }));

        izquierda.Controls.Add(CrearBoton("Ejemplo: pedido (5 rutas)",
            (_, _) => CargarEjemplo(Ejemplos.Pedido, "Almacén", "Cliente"), margenSuperior: 25));
        izquierda.Controls.Add(CrearBoton("Ejemplo: grafo clásico", (_, _) => CargarEjemplo(Ejemplos.Clasico, "A", "F")));
        izquierda.Controls.Add(CrearBoton("Limpiar grafo", (_, _) =>
        {
            _grafo.Limpiar();
            GrafoModificado();
        }));

        // Panel derecho: tabla de distancias, comparación de rutas y registro de pasos.
        var derecha = new Panel { Dock = DockStyle.Right, Width = 400, Padding = new Padding(8) };

        _tabla.Dock = DockStyle.Top;
        _tabla.Height = 200;
        _tabla.View = View.Details;
        _tabla.FullRowSelect = true;
        _tabla.GridLines = true;
        _tabla.Columns.Add("Nodo", 60);
        _tabla.Columns.Add("Distancia", 80);
        _tabla.Columns.Add("Previo", 60);
        _tabla.Columns.Add("Estado", 100);

        _rutas.Dock = DockStyle.Top;
        _rutas.Height = 170;
        _rutas.View = View.Details;
        _rutas.FullRowSelect = true;
        _rutas.GridLines = true;
        _rutas.MultiSelect = false;
        _rutas.HideSelection = false;
        _rutas.Columns.Add("#", 30);
        _rutas.Columns.Add("Costo", 55);
        _rutas.Columns.Add("vs. mejor", 65);
        _rutas.Columns.Add("Ruta", 600);
        _rutas.SelectedIndexChanged += (_, _) =>
        {
            _rutaSeleccionada = _rutas.SelectedItems.Count > 0 ? _rutas.SelectedItems[0].Tag as Ruta : null;
            _lienzo.Invalidate();
        };

        _registro.Dock = DockStyle.Fill;
        _registro.Multiline = true;
        _registro.ReadOnly = true;
        _registro.ScrollBars = ScrollBars.Vertical;
        _registro.Font = new Font("Consolas", 9f);

        derecha.Controls.Add(_registro);
        derecha.Controls.Add(new Label { Text = "Registro del algoritmo", Dock = DockStyle.Top, Height = 25, TextAlign = ContentAlignment.BottomLeft });
        derecha.Controls.Add(_rutas);
        derecha.Controls.Add(new Label { Text = "Comparación de rutas origen → destino (clic para ver)", Dock = DockStyle.Top, Height = 25, TextAlign = ContentAlignment.BottomLeft });
        derecha.Controls.Add(_tabla);
        derecha.Controls.Add(new Label { Text = "Tabla de distancias", Dock = DockStyle.Top, Height = 20 });

        _lienzo.Dock = DockStyle.Fill;
        _lienzo.BackColor = Color.White;
        _lienzo.Paint += Lienzo_Paint;
        _lienzo.MouseDown += Lienzo_MouseDown;
        _lienzo.MouseMove += Lienzo_MouseMove;
        _lienzo.MouseUp += (_, _) => _nodoArrastrado = null;

        var barraEstado = new StatusStrip();
        barraEstado.Items.Add(_estado);

        Controls.Add(izquierda);
        Controls.Add(derecha);
        Controls.Add(barraEstado);
        Controls.Add(_lienzo);
        _lienzo.BringToFront(); // el lienzo ocupa el espacio restante

        ActualizarAyuda();
    }

    private static Button CrearBoton(string texto, EventHandler alHacerClic, bool negrita = false, int margenSuperior = 5)
    {
        var boton = new Button
        {
            Text = texto,
            Width = 200,
            Height = 32,
            Margin = new Padding(3, margenSuperior, 3, 3)
        };
        if (negrita)
            boton.Font = new Font("Segoe UI", 9.5f, FontStyle.Bold);
        boton.Click += alHacerClic;
        return boton;
    }

    private void ActualizarAyuda()
    {
        _estado.Text = _modo switch
        {
            Modo.AgregarNodo => "Haga clic en un espacio vacío para crear un nodo.",
            Modo.AgregarArista => _nodoSeleccionado == null
                ? "Haga clic en el nodo de inicio de la arista."
                : $"Nodo {_nodoSeleccionado} seleccionado. Haga clic en el nodo final (peso {_peso.Value}).",
            Modo.Mover => "Arrastre un nodo para moverlo.",
            Modo.Eliminar => "Haga clic en un nodo o arista para eliminarlo.",
            _ => ""
        };
    }

    // ------------------------------------------------------------------ Eventos del lienzo

    private void Lienzo_MouseDown(object? sender, MouseEventArgs e)
    {
        var nodo = NodoEn(e.Location);

        switch (_modo)
        {
            case Modo.AgregarNodo:
                if (nodo == null)
                {
                    _grafo.AgregarNodo(e.Location);
                    GrafoModificado();
                }
                else
                {
                    _nodoArrastrado = nodo; // permite reubicar sin cambiar de modo
                }
                break;

            case Modo.AgregarArista:
                if (nodo == null)
                {
                    _nodoSeleccionado = null;
                }
                else if (_nodoSeleccionado == null)
                {
                    _nodoSeleccionado = nodo;
                }
                else if (nodo != _nodoSeleccionado)
                {
                    _grafo.AgregarArista(_nodoSeleccionado, nodo, (double)_peso.Value);
                    _nodoSeleccionado = null;
                    GrafoModificado();
                }
                ActualizarAyuda();
                _lienzo.Invalidate();
                break;

            case Modo.Mover:
                _nodoArrastrado = nodo;
                break;

            case Modo.Eliminar:
                if (nodo != null)
                {
                    _grafo.EliminarNodo(nodo);
                    GrafoModificado();
                }
                else if (AristaEn(e.Location) is { } arista)
                {
                    _grafo.EliminarArista(arista);
                    GrafoModificado();
                }
                break;
        }
    }

    private void Lienzo_MouseMove(object? sender, MouseEventArgs e)
    {
        if (_nodoArrastrado == null || e.Button != MouseButtons.Left)
            return;

        _nodoArrastrado.Posicion = new PointF(
            Math.Clamp(e.X, Radio, _lienzo.Width - Radio),
            Math.Clamp(e.Y, Radio, _lienzo.Height - Radio));
        _lienzo.Invalidate();
    }

    private Nodo? NodoEn(Point p) =>
        _grafo.Nodos.LastOrDefault(n => Distancia(n.Posicion, p) <= Radio);

    private Arista? AristaEn(Point p) =>
        _grafo.Aristas.FirstOrDefault(a => DistanciaASegmento(p, a.Origen.Posicion, a.Destino.Posicion) <= 6);

    private static double Distancia(PointF a, PointF b) =>
        Math.Sqrt((a.X - b.X) * (a.X - b.X) + (a.Y - b.Y) * (a.Y - b.Y));

    private static double DistanciaASegmento(PointF p, PointF a, PointF b)
    {
        var dx = b.X - a.X;
        var dy = b.Y - a.Y;
        var largo2 = dx * dx + dy * dy;
        if (largo2 == 0) return Distancia(p, a);
        var t = Math.Clamp(((p.X - a.X) * dx + (p.Y - a.Y) * dy) / largo2, 0, 1);
        return Distancia(p, new PointF(a.X + t * dx, a.Y + t * dy));
    }

    // ------------------------------------------------------------------ Lógica

    private void GrafoModificado()
    {
        ActualizarCombos();
        InvalidarResultado();
    }

    private void ActualizarCombos()
    {
        var origen = _origen.SelectedItem as Nodo;
        var destino = _destino.SelectedItem as Nodo;

        _origen.BeginUpdate();
        _destino.BeginUpdate();
        _origen.Items.Clear();
        _destino.Items.Clear();
        foreach (var n in _grafo.Nodos)
        {
            _origen.Items.Add(n);
            _destino.Items.Add(n);
        }
        _origen.EndUpdate();
        _destino.EndUpdate();

        if (origen != null && _grafo.Nodos.Contains(origen)) _origen.SelectedItem = origen;
        else if (_origen.Items.Count > 0) _origen.SelectedIndex = 0;

        if (destino != null && _grafo.Nodos.Contains(destino)) _destino.SelectedItem = destino;
        else if (_destino.Items.Count > 0) _destino.SelectedIndex = _destino.Items.Count - 1;
    }

    private void InvalidarResultado()
    {
        _resultado = null;
        _indicePaso = -1;
        CalcularRutas();
        MostrarResultado();
    }

    /// <summary>Llena la tabla con todas las rutas simples del origen al destino, de la más rápida a la más lenta.</summary>
    private void CalcularRutas()
    {
        _rutaSeleccionada = null;
        _rutasEncontradas = new List<Ruta>();
        if (_resultado != null && _destino.SelectedItem is Nodo destino)
            _rutasEncontradas = Rutas.TodasLasRutas(_grafo, _resultado.Origen, destino);

        _rutas.BeginUpdate();
        _rutas.Items.Clear();
        var mejor = _rutasEncontradas.FirstOrDefault()?.Costo ?? 0;
        for (var i = 0; i < _rutasEncontradas.Count; i++)
        {
            var ruta = _rutasEncontradas[i];
            var item = new ListViewItem((i + 1).ToString()) { Tag = ruta };
            item.SubItems.Add(Dijkstra.Formato(ruta.Costo));
            item.SubItems.Add(i == 0 || ruta.Costo == mejor ? "más rápida" : "+" + Dijkstra.Formato(ruta.Costo - mejor));
            item.SubItems.Add(ruta.ToString());
            if (ruta.Costo == mejor)
            {
                item.BackColor = Color.Honeydew;
                item.Font = new Font(_rutas.Font, FontStyle.Bold);
            }
            _rutas.Items.Add(item);
        }
        _rutas.EndUpdate();
    }

    private void EjecutarDijkstra()
    {
        if (_origen.SelectedItem is not Nodo origen)
        {
            MessageBox.Show(this, "Agregue nodos y seleccione un nodo origen.", "Dijkstra",
                MessageBoxButtons.OK, MessageBoxIcon.Information);
            return;
        }

        _resultado = Dijkstra.Ejecutar(_grafo, origen);
        _indicePaso = 0; // empezar mostrando el primer paso
        CalcularRutas();
        MostrarResultado();
    }

    private void MoverPaso(int delta)
    {
        if (_resultado == null)
        {
            EjecutarDijkstra();
            return;
        }

        var total = _resultado.Pasos.Count;
        var actual = _indicePaso < 0 ? total - 1 : _indicePaso;
        _indicePaso = Math.Clamp(actual + delta, 0, total - 1);
        MostrarResultado();
    }

    private PasoDijkstra? PasoVisible =>
        _resultado == null ? null
        : _indicePaso < 0 ? _resultado.Pasos[^1]
        : _resultado.Pasos[_indicePaso];

    private bool EsVistaFinal => _resultado != null && (_indicePaso < 0 || _indicePaso == _resultado.Pasos.Count - 1);

    private IReadOnlyList<Nodo> CaminoVisible()
    {
        if (_rutaSeleccionada != null)
            return _rutaSeleccionada.Nodos;
        if (_resultado == null || !EsVistaFinal || _destino.SelectedItem is not Nodo destino)
            return new List<Nodo>();
        return _resultado.CaminoHasta(destino);
    }

    private void MostrarResultado()
    {
        _anterior.Enabled = _siguiente.Enabled = _grafo.Nodos.Count > 0;
        _tabla.BeginUpdate();
        _tabla.Items.Clear();

        var paso = PasoVisible;
        if (_resultado == null || paso == null)
        {
            _registro.Text = "Construya un grafo y pulse \"Ejecutar Dijkstra\".";
        }
        else
        {
            foreach (var n in _grafo.Nodos)
            {
                var estado = n == paso.NodoActual ? "Actual"
                    : paso.Visitados.Contains(n) ? "Visitado"
                    : double.IsPositiveInfinity(paso.Distancias[n]) ? "Sin alcanzar"
                    : "En cola";
                var item = new ListViewItem(n.Nombre);
                item.SubItems.Add(Dijkstra.Formato(paso.Distancias[n]));
                item.SubItems.Add(paso.Previos[n]?.Nombre ?? "-");
                item.SubItems.Add(estado);
                if (n == paso.NodoActual) item.BackColor = Color.Moccasin;
                _tabla.Items.Add(item);
            }

            var total = _resultado.Pasos.Count;
            var indice = _indicePaso < 0 ? total - 1 : _indicePaso;
            var lineas = _resultado.Pasos.Take(indice + 1).Select(p => p.Descripcion).ToList();
            lineas.Insert(0, $"Paso {indice + 1} de {total}");
            lineas.Insert(1, new string('-', 36));

            if (EsVistaFinal && _destino.SelectedItem is Nodo destino)
            {
                var camino = _resultado.CaminoHasta(destino);
                lineas.Add("");
                lineas.Add(camino.Count == 0
                    ? $"No existe camino de {_resultado.Origen} a {destino}."
                    : $"Camino más corto {_resultado.Origen} → {destino}:\r\n  {string.Join(" → ", camino)}\r\n" +
                      $"  Costo total: {Dijkstra.Formato(_resultado.Distancias[destino])}");

                // Validación cruzada: la ruta de Dijkstra debe costar lo mismo que la mejor por fuerza bruta.
                if (camino.Count > 0 && _rutasEncontradas.Count > 0)
                {
                    var mejor = _rutasEncontradas[0].Costo;
                    var coincide = Math.Abs(mejor - _resultado.Distancias[destino]) < 1e-9;
                    lineas.Add(coincide
                        ? $"✔ Validado: es la más rápida de {_rutasEncontradas.Count} rutas evaluadas."
                        : $"✘ No coincide con la mejor ruta evaluada ({Dijkstra.Formato(mejor)}).");
                }
            }

            _registro.Text = string.Join("\r\n", lineas);
            _registro.SelectionStart = _registro.TextLength;
            _registro.ScrollToCaret();
        }

        _tabla.EndUpdate();
        _lienzo.Invalidate();
    }

    private void CargarEjemplo(Action<Grafo> crear, string origen, string destino)
    {
        _dirigido.Checked = false;
        crear(_grafo);
        GrafoModificado();
        _origen.SelectedItem = _grafo.Nodos.FirstOrDefault(n => n.Nombre == origen);
        _destino.SelectedItem = _grafo.Nodos.FirstOrDefault(n => n.Nombre == destino);
    }

    // ------------------------------------------------------------------ Dibujo

    private void Lienzo_Paint(object? sender, PaintEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

        var paso = PasoVisible;
        var camino = CaminoVisible();
        var colorCamino = _rutaSeleccionada != null ? Color.RoyalBlue : Color.Crimson;
        var aristasCamino = new HashSet<(Nodo, Nodo)>();
        for (var i = 0; i + 1 < camino.Count; i++)
            aristasCamino.Add((camino[i], camino[i + 1]));

        using var fuentePeso = new Font("Segoe UI", 9f, FontStyle.Bold);
        using var fuenteNodo = new Font("Segoe UI", 10f, FontStyle.Bold);
        using var fuenteDist = new Font("Segoe UI", 8.5f);

        foreach (var arista in _grafo.Aristas)
        {
            var enCamino = aristasCamino.Contains((arista.Origen, arista.Destino))
                           || (!_grafo.Dirigido && aristasCamino.Contains((arista.Destino, arista.Origen)));
            var enArbol = paso != null && !enCamino && EsAristaDeArbol(arista, paso);
            var evaluada = paso?.NodoActual != null && paso.VecinoEvaluado != null
                           && (arista.Origen == paso.NodoActual && arista.Destino == paso.VecinoEvaluado
                               || !_grafo.Dirigido && arista.Destino == paso.NodoActual && arista.Origen == paso.VecinoEvaluado);

            var color = enCamino ? colorCamino : evaluada ? Color.DarkOrange : enArbol ? Color.SeaGreen : Color.Gray;
            var grosor = enCamino || evaluada ? 4f : enArbol ? 2.5f : 1.5f;
            DibujarArista(g, arista, color, grosor, fuentePeso);
        }

        foreach (var nodo in _grafo.Nodos)
        {
            var relleno = Color.LightSkyBlue;
            if (paso != null)
            {
                if (nodo == paso.NodoActual) relleno = Color.Orange;
                else if (paso.Visitados.Contains(nodo)) relleno = Color.LightGreen;
            }
            if (camino.Contains(nodo)) relleno = _rutaSeleccionada != null ? Color.LightSteelBlue : Color.LightCoral;

            var borde = nodo == _nodoSeleccionado ? Color.Purple
                : nodo == _origen.SelectedItem as Nodo ? Color.DarkGreen
                : nodo == _destino.SelectedItem as Nodo ? Color.DarkRed
                : Color.SteelBlue;

            var rect = new RectangleF(nodo.Posicion.X - Radio, nodo.Posicion.Y - Radio, Radio * 2, Radio * 2);
            using (var pincel = new SolidBrush(relleno)) g.FillEllipse(pincel, rect);
            using (var lapiz = new Pen(borde, nodo == _nodoSeleccionado ? 4f : 2.5f)) g.DrawEllipse(lapiz, rect);

            using var formatoCentro = new StringFormat { Alignment = StringAlignment.Center, LineAlignment = StringAlignment.Center };
            var tamNombre = g.MeasureString(nodo.Nombre, fuenteNodo);
            if (tamNombre.Width <= Radio * 2 - 4)
            {
                g.DrawString(nodo.Nombre, fuenteNodo, Brushes.Black, rect, formatoCentro);
            }
            else
            {
                // Nombres largos: inicial dentro del círculo y nombre completo debajo.
                g.DrawString(nodo.Nombre[..1], fuenteNodo, Brushes.Black, rect, formatoCentro);
                var caja = new RectangleF(nodo.Posicion.X - tamNombre.Width / 2, rect.Bottom + 2, tamNombre.Width, tamNombre.Height);
                g.FillRectangle(Brushes.White, caja);
                g.DrawString(nodo.Nombre, fuenteNodo, Brushes.Black, caja.X, caja.Y);
            }

            if (paso != null)
            {
                var texto = "d=" + Dijkstra.Formato(paso.Distancias[nodo]);
                var tam = g.MeasureString(texto, fuenteDist);
                g.DrawString(texto, fuenteDist, Brushes.DimGray,
                    nodo.Posicion.X - tam.Width / 2, nodo.Posicion.Y - Radio - tam.Height - 1);
            }
        }

        DibujarLeyenda(g);
    }

    // Arista que forma parte del árbol de caminos más cortos construido hasta el paso actual.
    private bool EsAristaDeArbol(Arista arista, PasoDijkstra paso) =>
        paso.Previos[arista.Destino] == arista.Origen
        || !_grafo.Dirigido && paso.Previos[arista.Origen] == arista.Destino;

    private void DibujarArista(Graphics g, Arista arista, Color color, float grosor, Font fuente)
    {
        var a = arista.Origen.Posicion;
        var b = arista.Destino.Posicion;
        var dx = b.X - a.X;
        var dy = b.Y - a.Y;
        var largo = (float)Math.Sqrt(dx * dx + dy * dy);
        if (largo < 1) return;
        var ux = dx / largo;
        var uy = dy / largo;

        // En grafos dirigidos con aristas en ambos sentidos, se separan las líneas.
        var desplazamiento = 0f;
        if (_grafo.Dirigido && _grafo.Aristas.Any(x => x.Origen == arista.Destino && x.Destino == arista.Origen))
            desplazamiento = 7f;
        var ox = -uy * desplazamiento;
        var oy = ux * desplazamiento;

        var inicio = new PointF(a.X + ux * Radio + ox, a.Y + uy * Radio + oy);
        var fin = new PointF(b.X - ux * Radio + ox, b.Y - uy * Radio + oy);

        using var lapiz = new Pen(color, grosor);
        if (_grafo.Dirigido)
            lapiz.CustomEndCap = new AdjustableArrowCap(4, 5);
        g.DrawLine(lapiz, inicio, fin);

        var texto = Dijkstra.Formato(arista.Peso);
        var tam = g.MeasureString(texto, fuente);
        var medio = new PointF((inicio.X + fin.X) / 2 + ox * 1.5f, (inicio.Y + fin.Y) / 2 + oy * 1.5f);
        var caja = new RectangleF(medio.X - tam.Width / 2 - 2, medio.Y - tam.Height / 2, tam.Width + 4, tam.Height);
        g.FillRectangle(Brushes.White, caja);
        using var pincelTexto = new SolidBrush(color == Color.Gray ? Color.Black : color);
        g.DrawString(texto, fuente, pincelTexto, caja.X + 2, caja.Y);
    }

    private static void DibujarLeyenda(Graphics g)
    {
        var elementos = new (Color Color, string Texto)[]
        {
            (Color.LightSkyBlue, "Sin visitar"),
            (Color.Orange, "Nodo actual"),
            (Color.LightGreen, "Visitado"),
            (Color.LightCoral, "Camino más corto (Dijkstra)"),
            (Color.LightSteelBlue, "Ruta seleccionada en la tabla")
        };
        using var fuente = new Font("Segoe UI", 8.5f);
        var y = 10f;
        foreach (var (color, texto) in elementos)
        {
            using var pincel = new SolidBrush(color);
            g.FillEllipse(pincel, 10, y, 12, 12);
            g.DrawEllipse(Pens.SteelBlue, 10, y, 12, 12);
            g.DrawString(texto, fuente, Brushes.Black, 27, y - 2);
            y += 18;
        }
    }

    /// <summary>Panel con doble búfer para evitar parpadeo al redibujar.</summary>
    private sealed class PanelDibujo : Panel
    {
        public PanelDibujo()
        {
            DoubleBuffered = true;
            ResizeRedraw = true;
        }
    }
}
