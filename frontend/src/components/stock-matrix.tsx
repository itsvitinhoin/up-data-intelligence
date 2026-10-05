import { ListExport } from "@/components/exports";
import type { Product } from "@/types/domain";
export function StockMatrix({ product }: { product: Product }) {
  const variants = product.variants;
  if (!variants?.length)
    return <p className="muted">Estoque por tamanho e cor não disponível.</p>;
  const colors = [...new Set(variants.map((v) => v.color))],
    sizes = [...new Set(variants.map((v) => v.size))];
  return (
    <>
      <ListExport rows={variants} name={`estoque-${product.sku}`} />
      <div className="table-scroll">
        <table className="stock-matrix num">
          <caption className="sr-only">Estoque por tamanho e cor</caption>
          <thead>
            <tr>
              <th>Cor / tamanho</th>
              {sizes.map((size) => (
                <th key={size ?? "unknown"}>
                  {size ?? "Tamanho não informado"}
                </th>
              ))}
              <th>Total</th>
            </tr>
          </thead>
          <tbody>
            {colors.map((color) => {
              const rows = variants.filter((v) => v.color === color);
              return (
                <tr key={color ?? "unknown"}>
                  <th>{color ?? "Cor não informada"}</th>
                  {sizes.map((size) => {
                    const cell = rows.filter((v) => v.size === size);
                    const stock =
                      cell.length && cell.every((v) => v.stock !== null)
                        ? cell.reduce((sum, v) => sum + (v.stock ?? 0), 0)
                        : null;
                    return (
                      <td
                        key={size ?? "unknown"}
                        className={stock === 0 ? "stock-zero" : ""}
                      >
                        {stock === null ? "—" : stock}
                        <small>
                          {stock === 0
                            ? "Sem estoque"
                            : stock === null
                              ? "Não informado"
                              : "peças"}
                        </small>
                      </td>
                    );
                  })}
                  <td>
                    {rows.some((v) => v.stock === null)
                      ? "—"
                      : rows.reduce((s, v) => s + (v.stock ?? 0), 0)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <p className="metric-hint mt-3">
        Zero indica ruptura da variante. Traço indica estoque desconhecido.
        {product.catalog
          ? ` Estoque das variantes do catálogo em ${new Date(product.catalog.snapshot_as_of).toLocaleDateString("pt-BR")}; traços não comprovam ruptura.`
          : " Quantidades demonstrativas."}
      </p>
    </>
  );
}
