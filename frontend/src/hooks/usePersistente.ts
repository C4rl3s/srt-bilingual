import { useEffect, useState } from 'react'

/**
 * `useState` que además se guarda en `localStorage`, para que la preferencia
 * (árbol plegado, vista de cada carpeta…) sobreviva a recargar la página.
 *
 * Es un hook propio: una función que empieza por `use` y combina hooks de React.
 * Se usa igual que `useState`, con una clave de más.
 */
export function usePersistente<T>(clave: string, inicial: T) {
  // Inicialización perezosa: la función solo se ejecuta en el primer render, así
  // que no se lee `localStorage` en cada pintado.
  const [valor, setValor] = useState<T>(() => {
    try {
      const guardado = localStorage.getItem(clave)
      return guardado === null ? inicial : (JSON.parse(guardado) as T)
    } catch {
      return inicial // modo privado, datos corruptos…: se sigue sin preferencia
    }
  })

  useEffect(() => {
    try {
      localStorage.setItem(clave, JSON.stringify(valor))
    } catch {
      // Sin almacenamiento la app funciona igual; solo no recuerda.
    }
  }, [clave, valor])

  return [valor, setValor] as const
}
