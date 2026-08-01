import { useEffect, useRef } from "react";
import {
  ColorType,
  LineStyle,
  createChart,
  type IChartApi,
  type ISeriesApi,
  type UTCTimestamp,
} from "lightweight-charts";

export interface ChartSeries {
  id: string;
  label: string;
  color: string;
  /** Points ; les valeurs nulles créent un trou plutôt qu'un segment faux. */
  data: { time: string; value: number | null }[];
  dashed?: boolean;
  area?: boolean;
  width?: number;
}

function toTime(iso: string): UTCTimestamp {
  return (Date.parse(iso + "T00:00:00Z") / 1000) as UTCTimestamp;
}

/** Graphique linéaire, adossé à lightweight-charts, accordé au thème sombre. */
export function Chart({
  series,
  height = 320,
  priceFormat,
}: {
  series: ChartSeries[];
  height?: number;
  priceFormat?: { precision: number; minMove: number };
}) {
  const host = useRef<HTMLDivElement>(null);
  const chartRef = useRef<IChartApi | null>(null);
  const seriesRef = useRef<Map<string, ISeriesApi<"Line" | "Area">>>(new Map());

  useEffect(() => {
    if (!host.current) return;

    const chart = createChart(host.current, {
      height,
      layout: {
        background: { type: ColorType.Solid, color: "transparent" },
        textColor: "#9aa5ba",
        fontSize: 11,
        fontFamily: "ui-monospace, Consolas, monospace",
      },
      grid: {
        vertLines: { color: "rgba(35,43,59,0.5)" },
        horzLines: { color: "rgba(35,43,59,0.5)" },
      },
      rightPriceScale: { borderColor: "#232b3b" },
      timeScale: { borderColor: "#232b3b", timeVisible: false },
      crosshair: {
        mode: 1,
        vertLine: { color: "#5aa9ff", width: 1, style: LineStyle.Dotted, labelBackgroundColor: "#2b5f9e" },
        horzLine: { color: "#5aa9ff", width: 1, style: LineStyle.Dotted, labelBackgroundColor: "#2b5f9e" },
      },
      handleScale: { axisPressedMouseMove: { time: true, price: false } },
    });
    chartRef.current = chart;

    const observer = new ResizeObserver((entries) => {
      const width = entries[0]?.contentRect.width;
      if (width) chart.applyOptions({ width });
    });
    observer.observe(host.current);

    return () => {
      observer.disconnect();
      chart.remove();
      chartRef.current = null;
      seriesRef.current.clear();
    };
  }, [height]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart) return;

    // Les séries absentes du nouveau jeu sont retirées avant d'ajouter les autres.
    for (const [id, handle] of seriesRef.current) {
      if (!series.some((s) => s.id === id)) {
        chart.removeSeries(handle);
        seriesRef.current.delete(id);
      }
    }

    for (const spec of series) {
      let handle = seriesRef.current.get(spec.id);
      if (!handle) {
        const options = {
          color: spec.color,
          lineWidth: (spec.width ?? 2) as 1 | 2 | 3 | 4,
          lineStyle: spec.dashed ? LineStyle.Dashed : LineStyle.Solid,
          priceLineVisible: false,
          lastValueVisible: true,
          title: spec.label,
          ...(priceFormat ? { priceFormat: { type: "price" as const, ...priceFormat } } : {}),
        };
        handle = spec.area
          ? chart.addAreaSeries({
              ...options,
              lineColor: spec.color,
              topColor: spec.color + "33",
              bottomColor: spec.color + "05",
            })
          : chart.addLineSeries(options);
        seriesRef.current.set(spec.id, handle);
      }
      handle.setData(
        spec.data
          .filter((point) => point.value !== null && Number.isFinite(point.value))
          .map((point) => ({ time: toTime(point.time), value: point.value as number })),
      );
    }

    chart.timeScale().fitContent();
  }, [series, priceFormat]);

  return <div ref={host} className="chart-host" />;
}
