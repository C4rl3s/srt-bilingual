# Frontend — srt-bilingual

SPA en React + TypeScript sobre Vite. Una sola página con dos bloques: las carpetas
vigiladas arriba y el árbol de la biblioteca abajo.

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
├── main.tsx              punto de entrada
├── App.tsx               compone los dos bloques y guarda el estado compartido
├── types.ts              espejo TypeScript de los DTOs del backend
├── api/client.ts         único punto de salida HTTP
└── components/
    ├── PanelCarpetas.tsx     carpetas, casillas, contadores y botón de escanear
    ├── SelectorCarpeta.tsx   modal para navegar el disco y elegir una carpeta
    └── ArbolSubtitulos.tsx   árbol recursivo, plegable, hasta cada capítulo
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

- **El explorador de carpetas lo sirve el backend.** El navegador no puede dar la
  ruta absoluta de una carpeta del sistema, así que `SelectorCarpeta` navega
  pidiendo `/api/fs/roots` y `/api/fs/browse`.
- **El árbol se pinta recursivamente** y cada nodo guarda su propio estado de
  plegado con `useState`; no hay estado global de expansión.
- Sin router ni librería de estado: la aplicación es una sola pantalla.
