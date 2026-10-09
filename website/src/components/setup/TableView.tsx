import { InlineText } from './InlineText';

interface TableViewProps {
  /** Two columns; the first row is the header. */
  rows: readonly (readonly [string, string])[];
}

/** A small two-column table that scrolls sideways on a narrow screen. */
export function TableView({ rows }: TableViewProps) {
  const [header, ...body] = rows;
  if (header === undefined) return null;
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse text-left text-sm">
        <thead>
          <tr>
            {header.map((cell) => (
              <th key={cell} scope="col" className="border-b border-line-strong py-2 pr-4 font-semibold">
                <InlineText text={cell} />
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {body.map((row) => (
            <tr key={row.join('|')}>
              {row.map((cell, index) => (
                <td key={`${index}-${cell}`} className="border-b border-line py-2 pr-4 align-top">
                  <InlineText text={cell} />
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
