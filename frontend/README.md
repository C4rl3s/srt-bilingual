# Frontend — srt-bilingual

SPA en React + TypeScript sobre Vite. Tres secciones (Biblioteca, Trabajos y
Renombrar para Plex) más la gestión de carpetas. El diseño aprobado está resumido en
`docs/plans/plan-fase3.md`, punto 10 del diseño.

## Puesta en marcha

```powershell
npm install
npm run dev      # http://localhost:5173
```

Necesita el backend levantado en el puerto 8000 (ver `../backend/README.md`).

## Comandos

```powershell
npm run dev       # servidor de desarrollo con recarga en caliente
npm run build     # comprueba tipos con tsc y compila a dist/
npm run preview   # sirve lo compilado
npm run lint      # oxlint
```

## Estructura

```
src/
├── main.tsx                 punto de entrada
├── App.tsx                  esqueleto: cabecera, sección activa y datos compartidos
├── index.css                tokens del diseño (colores, tipografías) y base
├── App.css                  estilos por pantalla, y la adaptación a móvil al final
├── types.ts                 espejo TypeScript de los DTOs del backend
├── api/client.ts            único punto de salida HTTP
├── hooks/
│   ├── useTrabajos.ts       trabajos con sondeo mientras haya alguno activo
│   └── usePersistente.ts    useState guardado en localStorage
├── utils/
│   ├── formato.ts           números, fechas y títulos legibles
│   ├── cupos.ts             cupos de los proveedores y previsión del reparto
│   └── biblioteca.ts        qué carpetas salen en el árbol, qué obras en cada una, filtros
└── components/
    ├── Cabecera.tsx          marca, pestañas, trabajo en curso y cupo
    ├── Trabajos.tsx          decisiones pendientes, en curso, historial y cupo
    ├── Renombrado.tsx        actual → nuevo con casillas
    ├── Carpetas.tsx          carpetas vigiladas, escaneo y explorador del disco
    ├── Iconos.tsx            iconos SVG en línea
    └── biblioteca/
        ├── Biblioteca.tsx        las tres columnas y las preferencias recordadas
        ├── ArbolCarpetas.tsx     árbol plegable (componente recursivo)
        ├── ContenidoCarpeta.tsx  mosaico o lista, filtros y selección
        ├── PanelDetalle.tsx      origen, coreano, fusión, muestra y generar
        └── PanelSeleccion.tsx    resumen de la selección y cupo que gastará
```

## Cómo se habla con el backend

Todas las llamadas van a **`/api/...`**, nunca a `http://localhost:8000`. El proxy
de Vite (`vite.config.ts`) reenvía `/api/*` al backend quitando el prefijo, así que
el mismo código vale en desarrollo y en producción, donde ambos se sirven del mismo
origen.

`src/types.ts` es un espejo **manual** de los schemas de Pydantic: TypeScript no
puede comprobar lo que llega por la red, solo lo que nosotros le prometemos. Si
cambia un DTO en el backend, hay que actualizarlo aquí.

## Detalles que conviene saber

- **Sin router ni librería de estado.** Cuatro secciones caben en un `useState` de
  `App`, que guarda lo que comparten (árbol, carpetas, trabajos, cupo).
- **El árbol solo muestra carpetas que agrupan** (con subcarpetas o varias obras,
  como una temporada). La carpeta de cada película no sale: sus obras se ven al
  elegir `Pelis` (`utils/biblioteca.ts`, `esNavegable`).
- **Preferencias recordadas en `localStorage`**: árbol plegado, carpetas
  desplegadas, carpeta elegida y la vista (mosaico o lista) de cada carpeta.
- **El progreso se ve por sondeo**: mientras haya trabajos activos se pregunta cada
  2 s; al terminar el último se recargan el árbol y el cupo.
- **El explorador de carpetas lo sirve el backend.** El navegador no puede dar la
  ruta absoluta de una carpeta del sistema, así que se navega con
  `/api/fs/roots` y `/api/fs/browse`.
- **Pósteres de pega**: un color estable por obra, derivado de su ruta. Traer las
  carátulas reales (de Plex, por ejemplo) queda como mejora.
- **Móvil (≤ 900 px)**: el árbol pasa a ser un cajón que se abre con ☰ y el panel de
  la obra, una hoja inferior.
- Tipografías de Google Fonts (`index.html`): Bricolage Grotesque, Figtree, Noto
  Sans KR y JetBrains Mono.
