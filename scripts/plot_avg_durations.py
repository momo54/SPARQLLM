
import pandas as pd
import matplotlib.pyplot as plt
import sys

def main():
    if len(sys.argv) > 1:
        csv_path = sys.argv[1]
    else:
        csv_path = "avg.csv"
    if len(sys.argv) > 2:
        out_png = sys.argv[2]
    else:
        out_png = "durations_by_model.png"
    df = pd.read_csv(csv_path)

    def clean_tool(tool):
        if tool.startswith("urn:mcp:handle:"):
            return tool.replace("urn:mcp:handle:", "")
        if tool.startswith("urn:mcp:tool:"):
            return tool.replace("urn:mcp:tool:", "")
        return tool

    df["tool"] = df["tool"].apply(clean_tool)

    pivot = df.pivot(index="model", columns="tool", values="avg_duration").fillna(0)

    segment_order = list(pivot.columns)
    colors = plt.cm.tab20.colors[:len(segment_order)]

    ax = pivot[segment_order].plot(kind="bar", stacked=True, color=colors, figsize=(10,6))

    for i, model in enumerate(pivot.index):
        total = 0
        for j, seg in enumerate(segment_order):
            val = pivot.loc[model, seg]
            if val > 0:
                ax.text(i, total + val/2, f"{val:.2f}s", ha="center", va="center", color="white", fontsize=11)
            total += val
        ax.text(i, total + 0.05, f"{total:.2f}s", ha="center", va="bottom", color="black", fontsize=13, fontweight="bold")

    plt.title("Average durations per MCP call by model")
    plt.ylabel("Average duration (s)")
    plt.xlabel("Model")
    plt.xticks(rotation=20)
    plt.legend(title="Segment", bbox_to_anchor=(1.05, 1), loc="upper left")
    plt.tight_layout()
    plt.savefig(out_png)
    plt.show()

if __name__ == "__main__":
    main()

def clean_tool(tool):
    if tool.startswith("urn:mcp:handle:"):
        return tool.replace("urn:mcp:handle:", "")
    if tool.startswith("urn:mcp:tool:"):
        return tool.replace("urn:mcp:tool:", "")
    return tool

df["tool"] = df["tool"].apply(clean_tool)

# Pivot pour avoir chaque segment en colonne
pivot = df.pivot(index="model", columns="tool", values="avg_duration").fillna(0)

segment_order = list(pivot.columns)
colors = plt.cm.tab20.colors[:len(segment_order)]

ax = pivot[segment_order].plot(kind="bar", stacked=True, color=colors, figsize=(10,6))

for i, model in enumerate(pivot.index):
    total = 0
    for j, seg in enumerate(segment_order):
        val = pivot.loc[model, seg]
        if val > 0:
            ax.text(i, total + val/2, f"{val:.2f}s", ha="center", va="center", color="white", fontsize=11)
        total += val
    ax.text(i, total + 0.05, f"{total:.2f}s", ha="center", va="bottom", color="black", fontsize=13, fontweight="bold")

plt.title("Average durations per MCP call by model")
plt.ylabel("Average duration (s)")
plt.xlabel("Model")
plt.xticks(rotation=20)
plt.legend(title="Segment", bbox_to_anchor=(1.05, 1), loc="upper left")
plt.tight_layout()
plt.savefig("durations_by_model.png")
plt.show()
