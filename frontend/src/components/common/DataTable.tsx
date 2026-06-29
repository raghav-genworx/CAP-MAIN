import type { ReactNode } from "react";

interface DataTableColumn<T> {
  header: string;
  key: string;
  render: (row: T) => ReactNode;
}

interface DataTableProps<T> {
  columns: DataTableColumn<T>[];
  emptyState?: ReactNode;
  getRowKey: (row: T) => string;
  isLoading?: boolean;
  rows: T[];
}

export function DataTable<T>({
  columns,
  emptyState,
  getRowKey,
  isLoading = false,
  rows,
}: DataTableProps<T>) {
  if (isLoading) {
    return <p className="empty-state">Loading...</p>;
  }

  if (!rows.length) {
    return emptyState ? <>{emptyState}</> : <p className="empty-state">No records found.</p>;
  }

  return (
    <div className="data-table-wrap">
      <table className="data-table">
        <thead>
          <tr>
            {columns.map((column) => (
              <th key={column.key}>{column.header}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={getRowKey(row)}>
              {columns.map((column) => (
                <td key={column.key}>{column.render(row)}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
