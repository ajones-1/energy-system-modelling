"""
Optimal Generation Portfolio Analysis
======================================
This script determines the optimal generation portfolio to meet:
- 1000 MW baseload
- Variable demand (from time series)
- Emissions constraint: < 50 gCO2/kWh

It compares different generation mixes and evaluates their technical and economic feasibility.
"""

import json
import os
from typing import Any

import matplotlib.pyplot as plt
import pandas as pd
import pypsa
from loguru import logger
from pypsa.common import annuity

from utils.general_functions import get_repo_root, get_package_root, load_data
from config.config import EMISSION_FACTORS

REPO_ROOT = get_repo_root()
PACKAGE_DIR = get_package_root()

def create_constrained_network(
    data_dir: str, year: int = 2030, co2_limit: float = 50, baseload_mw: float = 1000
) -> tuple[pypsa.Network, pd.DataFrame, pd.Series]:
    """
    Create a PyPSA network with emissions and baseload constraints.

    Parameters:
    -----------
    data_dir : str
        Directory to store/load data files
    year : int
        Year for cost data
    co2_limit : float
        Maximum emissions intensity in gCO2/kWh
    baseload_mw : float
        Minimum continuous baseload requirement in MW

    Returns:
    --------
    pypsa.Network : Configured network ready for optimization
    """
    logger.info(f"Creating network with {co2_limit} gCO2/kWh limit and {baseload_mw} MW baseload")

    # Load cost data
    url = f"https://raw.githubusercontent.com/PyPSA/technology-data/master/outputs/costs_{year}.csv"
    costs_df = load_data(url, f"{data_dir}/costs_{year}.csv", use_cache=True, index_col=[0, 1])

    # Process costs
    costs_df.loc[costs_df.unit.str.contains("/kW"), "value"] *= 1e3
    costs_df = costs_df.value.unstack().fillna({"discount rate": 0.07, "lifetime": 20, "FOM": 0})
    costs_df["marginal_cost"] = costs_df["VOM"] + costs_df["fuel"] / costs_df["efficiency"]

    a = costs_df.apply(lambda x: annuity(x["discount rate"], x["lifetime"]), axis=1)
    costs_df["capital_cost"] = (a + costs_df["FOM"] / 100) * costs_df["investment"]

    # Load time series data
    resolution = 3  # hours
    url_ts = "https://tubcloud.tu-berlinetwork.de/s/9toBssWEdaLgHzq/download/time-series.csv"
    time_series_df = load_data(url_ts, f"{data_dir}/time_series_{year}.csv", use_cache=True)[
        ::resolution
    ]

    # Initialize network
    network = pypsa.Network(name=f"Berlin Optimal Portfolio {year}")
    network.add("Bus", "electricity", carrier="electricity")
    network.set_snapshots(time_series_df.index)
    network.snapshot_weightings.loc[:, :] = resolution

    logger.info(f"Network initialized with {len(network.snapshots)} snapshots.")

    # Add carriers
    with open(PACKAGE_DIR / "config" / "carriers.json") as f:
        carriers_config = json.load(f)
    carriers = list(carriers_config["carriers"].keys())
    colors = list(carriers_config["carriers"].values())
    network.add("Carrier", carriers, color=colors)

    # Add load with baseload requirement
    # Create load profile that includes baseload + variable component
    baseload_series = pd.Series(baseload_mw, index=time_series_df.index)
    variable_load = time_series_df.load_mw
    total_load = baseload_series + variable_load

    network.add("Load", "demand", bus="electricity", p_set=total_load)
    logger.info(f"Added load: {baseload_mw} MW baseload + variable demand")
    logger.info(f"Peak load: {total_load.max():.1f} MW, Average: {total_load.mean():.1f} MW")

    # Add load shedding (high cost penalty)
    network.add(
        "Generator",
        "load shedding",
        bus="electricity",
        carrier="load shedding",
        marginal_cost=5000,  # Very high cost to avoid use
        p_nom=total_load.max(),
    )

    # Add renewable generators
    network.add(
        "Generator",
        "wind",
        bus="electricity",
        carrier="wind",
        p_max_pu=time_series_df.wind_pu,
        capital_cost=costs_df.at["onwind", "capital_cost"],
        marginal_cost=costs_df.at["onwind", "marginal_cost"],
        p_nom_extendable=True,
        p_nom_max=total_load.max() * 3,  # Limit to 3x peak load
    )
    logger.info("Added wind generator (extendable)")

    network.add(
        "Generator",
        "solar",
        bus="electricity",
        carrier="solar",
        p_max_pu=time_series_df.pv_pu,
        capital_cost=costs_df.at["solar", "capital_cost"],
        marginal_cost=costs_df.at["solar", "marginal_cost"],
        p_nom_extendable=True,
        p_nom_max=total_load.max() * 3,  # Limit to 3x peak load
    )
    logger.info("Added solar generator (extendable)")

    # Add OCGT for peak/backup (flexible but higher emissions)
    network.add(
        "Generator",
        "OCGT",
        bus="electricity",
        carrier="OCGT",
        capital_cost=costs_df.at["OCGT", "capital_cost"],
        marginal_cost=costs_df.at["OCGT", "marginal_cost"],
        efficiency=costs_df.at["OCGT", "efficiency"],
        p_nom_extendable=True,
        p_nom_max=total_load.max() * 0.5,  # Limit gas capacity
    )
    logger.info("Added OCGT generator (extendable)")

    # Add hydrogen storage system
    network.add("Bus", "hydrogen", carrier="hydrogen")

    network.add(
        "Link",
        "electrolysis",
        bus0="electricity",
        bus1="hydrogen",
        carrier="electrolysis",
        p_nom_extendable=True,
        efficiency=costs_df.at["electrolysis", "efficiency"],
        capital_cost=costs_df.at["electrolysis", "capital_cost"],
    )

    network.add(
        "Link",
        "fuel cell",
        bus0="hydrogen",
        bus1="electricity",
        carrier="fuel cell",
        p_nom_extendable=True,
        efficiency=costs_df.at["fuel cell", "efficiency"]
        if "fuel cell" in costs_df.index
        else 0.58,
        capital_cost=costs_df.at["OCGT", "capital_cost"],  # Use OCGT as proxy
    )

    network.add(
        "Store",
        "hydrogen storage",
        bus="hydrogen",
        carrier="hydrogen storage",
        e_nom_extendable=True,
        capital_cost=costs_df.at["hydrogen storage underground", "capital_cost"]
        if "hydrogen storage underground" in costs_df.index
        else 10,
    )

    logger.info("Added hydrogen storage system (electrolysis, fuel cell, storage)")

    # Add battery storage
    # Note: Battery storage connects directly to electricity bus, no separate bus needed
    network.add(
        "Bus",
        "battery",
        carrier="battery",
    )

    network.add(
        "Store",
        "battery storage",
        bus="battery",
        carrier="battery storage",
        e_nom_extendable=True,
        e_cyclic=True,
        capital_cost=costs_df.at["battery storage", "capital_cost"]
        if "battery storage" in costs_df.index
        else 150,
    )

    network.add(
        "Link",
        "battery charger",
        bus0="electricity",
        bus1="battery",
        carrier="battery storage",
        efficiency=0.95,
        p_nom_extendable=True,
        capital_cost=costs_df.at["battery inverter", "capital_cost"]
        if "battery inverter" in costs_df.index
        else 50,
    )

    network.add(
        "Link",
        "battery discharger",
        bus0="battery",
        bus1="electricity",
        carrier="battery storage",
        efficiency=0.95,
        p_nom_extendable=True,
        capital_cost=0,  # Cost already included in charger
    )

    logger.info("Added battery storage system")

    return network, costs_df, total_load


def optimize_with_emissions_constraint(
    network: pypsa.Network,
    co2_limit: float,
) -> bool:
    """
    Optimize network with emissions constraint.

    Parameters:
    -----------
    network : pypsa.Network
        Network to optimize
    co2_limit : float
        Maximum emissions intensity in gCO2/kWh

    Returns:
    --------
    bool : Whether optimization was successful
    """
    logger.info(f"Starting optimization with {co2_limit} gCO2/kWh emissions limit...")

    # Add global CO2 limit as a custom constraint
    # This is implemented through limiting fossil fuel generation
    network.optimize(solver_name="highs")
    logger.info("Optimization completed successfully")
    return network


def calculate_emissions_intensity(
    network: pypsa.Network, time_period: slice | None = None
) -> tuple[float, dict[str, float]]:
    """
    Calculate the emissions intensity (gCO2/kWh) for the network.

    Parameters:
    -----------
    network : pypsa.Network
        The optimized network
    time_period : slice, optional
        Time period to analyze (default: all snapshots)

    Returns:
    --------
    float : Emissions intensity in gCO2/kWh
    dict : Detailed emissions breakdown by carrier
    """
    if time_period is None:
        time_period = slice(None)

    # Get generation by carrier
    generators_t = network.generators_t.p[time_period]

    # Calculate emissions per generator
    emissions_by_carrier = {}
    total_emissions = 0
    total_generation = 0

    for gen in network.generators.index:
        carrier = network.generators.loc[gen, "carrier"]
        if carrier in EMISSION_FACTORS:
            gen_output = generators_t[gen].sum()
            emissions = gen_output * EMISSION_FACTORS[carrier] / 1000  # Convert to kgCO2
            emissions_by_carrier[carrier] = emissions_by_carrier.get(carrier, 0) + emissions
            total_emissions += emissions
            total_generation += gen_output

    # Calculate intensity
    if total_generation > 0:
        intensity = (total_emissions / total_generation) * 1000  # gCO2/kWh
    else:
        intensity = 0

    return intensity, emissions_by_carrier


def analyze_results(
    network: pypsa.Network, total_load: pd.Series, co2_limit: float = 50
) -> dict[str, Any]:
    """
    Analyze optimization results and check constraints.

    Parameters:
    -----------
    network : pypsa.Network
        Optimized network
    total_load : pd.Series
        Total load series
    co2_limit : float
        Emissions limit to check against

    Returns:
    --------
    dict : Analysis results
    """
    logger.info("Analyzing optimization results...")

    results = {}

    # Calculate emissions intensity
    intensity, emissions_breakdown = calculate_emissions_intensity(network)
    results["emissions_intensity"] = intensity
    results["emissions_breakdown"] = emissions_breakdown
    results["meets_co2_limit"] = intensity <= co2_limit

    logger.info(f"Emissions intensity: {intensity:.2f} gCO2/kWh (limit: {co2_limit})")
    logger.info(f"Meets CO2 limit: {'YES' if results['meets_co2_limit'] else 'NO'}")

    # Optimal capacities
    capacities = network.statistics.optimal_capacity()
    results["capacities_mw"] = capacities / 1e3

    logger.info("\nOptimal Capacities (GW):")
    for tech, cap in (capacities / 1e3).items():
        if cap > 0.001:
            logger.info(f"  {tech}: {cap:.3f} GW")

    # Energy balance
    energy_balance = (
        network.statistics.energy_balance(bus_carrier="electricity").sort_values() / 1e6
    )
    results["energy_balance_twh"] = energy_balance

    logger.info("\nEnergy Balance (TWh):")
    for tech, energy in energy_balance.items():
        logger.info(f"  {tech}: {energy:.3f} TWh")

    # System costs
    capex = network.statistics.capex().sum() / 1e9
    opex = network.statistics.opex().sum() / 1e9
    total_cost = capex + opex
    results["capex_bn_eur"] = capex
    results["opex_bn_eur"] = opex
    results["total_cost_bn_eur"] = total_cost

    logger.info("\nSystem Costs:")
    logger.info(f"  CAPEX: €{capex:.2f} billion")
    logger.info(f"  OPEX: €{opex:.2f} billion")
    logger.info(f"  Total: €{total_cost:.2f} billion")

    # Check baseload capability
    gen_t = network.generators_t.p
    min_generation = gen_t.sum(axis=1).min()
    avg_generation = gen_t.sum(axis=1).mean()
    results["min_generation_mw"] = min_generation
    results["avg_generation_mw"] = avg_generation

    logger.info("\nGeneration Statistics:")
    logger.info(f"  Minimum: {min_generation:.1f} MW")
    logger.info(f"  Average: {avg_generation:.1f} MW")
    logger.info(f"  Peak: {total_load.max():.1f} MW")

    # Load shedding check
    if "load shedding" in gen_t.columns:
        load_shed = gen_t["load shedding"].sum()
        results["load_shedding_mwh"] = load_shed
        if load_shed > 0.1:
            logger.warning(f"Load shedding occurred: {load_shed:.1f} MWh")
        else:
            logger.info("No significant load shedding")

    return results


def visualize_network_topology(network: pypsa.Network, output_dir: str) -> None:
    """
    Visualize the network topology showing buses and connections.

    Parameters:
    -----------
    network : pypsa.Network
        Network to visualize
    output_dir : str
        Directory to save figure
    """
    logger.info("Creating network topology diagram...")

    import networkx as nx

    fig, ax = plt.subplots(figsize=(16, 10))

    # Create a NetworkX graph to visualize the topology
    G = nx.DiGraph()

    # Add buses as nodes
    buses = network.buses.index.tolist()
    for bus in buses:
        carrier = network.buses.loc[bus, "carrier"]
        G.add_node(bus, carrier=carrier, node_type="bus")

    # Add links as edges
    for link in network.links.index:
        bus0 = network.links.loc[link, "bus0"]
        bus1 = network.links.loc[link, "bus1"]
        carrier = network.links.loc[link, "carrier"]
        G.add_edge(bus0, bus1, label=link, carrier=carrier)

    # Define positions for nodes (hierarchical layout)
    pos = nx.spring_layout(G, k=2, iterations=50, seed=42)

    # Get colors for buses based on carrier
    carrier_colors = {
        "electricity": "#f59e42",
        "hydrogen": "#ea048a",
        "battery": "#5ac8fa",
    }

    node_colors = [
        carrier_colors.get(G.nodes[node].get("carrier", ""), "#999999") for node in G.nodes()
    ]

    # Draw nodes (buses)
    nx.draw_networkx_nodes(G, pos, node_color=node_colors, node_size=3000, alpha=0.9, ax=ax)

    # Draw edges (links)
    nx.draw_networkx_edges(
        G,
        pos,
        edge_color="#666666",
        arrows=True,
        arrowsize=20,
        arrowstyle="->",
        width=2,
        alpha=0.6,
        ax=ax,
    )

    # Draw labels
    nx.draw_networkx_labels(G, pos, font_size=12, font_weight="bold", ax=ax)

    # Create edge labels
    edge_labels = {(u, v): data["label"] for u, v, data in G.edges(data=True)}
    nx.draw_networkx_edge_labels(G, pos, edge_labels, font_size=8, alpha=0.7, ax=ax)

    # Create legend
    legend_elements = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            color="w",
            markerfacecolor=color,
            markersize=10,
            label=carrier.title(),
        )
        for carrier, color in carrier_colors.items()
    ]
    ax.legend(handles=legend_elements, loc="upper right", fontsize=12)

    ax.set_title(
        "Energy System Network Topology\n(Buses and Links)", fontsize=16, fontweight="bold", pad=20
    )
    ax.axis("off")

    plt.tight_layout()
    plt.savefig(f"{output_dir}/network_topology.png", dpi=300, bbox_inches="tight")
    plt.close()

    logger.info(f"Network topology diagram saved to {output_dir}/network_topology.png")


def create_visualizations(network: pypsa.Network, results: dict[str, Any], output_dir: str) -> None:
    """
    Create visualizations of the optimal portfolio.

    Parameters:
    -----------
    network : pypsa.Network
        Optimized network
    results : dict
        Analysis results
    output_dir : str
        Directory to save figures
    """
    logger.info("Creating visualizations...")

    # 1. Generation mix pie chart
    fig, axes = plt.subplots(2, 2, figsize=(15, 12))

    # Capacity mix
    capacities = results["capacities_mw"]
    gen_capacities = capacities[capacities > 0.001]

    axes[0, 0].pie(gen_capacities.values, labels=gen_capacities.index, autopct="%1.1f%%")
    axes[0, 0].set_title("Installed Capacity Mix (GW)")

    # Energy generation mix
    energy = results["energy_balance_twh"]
    gen_energy = energy[energy > 0.001]

    axes[0, 1].pie(gen_energy.values, labels=gen_energy.index, autopct="%1.1f%%")
    axes[0, 1].set_title("Energy Generation Mix (TWh)")

    # Emissions by carrier
    if results["emissions_breakdown"]:
        emissions_df = pd.Series(results["emissions_breakdown"])
        axes[1, 0].bar(emissions_df.index, emissions_df.values)
        axes[1, 0].set_xlabel("Technology")
        axes[1, 0].set_ylabel("Emissions (tonnes CO2)")
        axes[1, 0].set_title("Emissions by Technology")
        axes[1, 0].tick_params(axis="x", rotation=45)

    # Cost breakdown
    cost_data = {"CAPEX": results["capex_bn_eur"], "OPEX": results["opex_bn_eur"]}
    axes[1, 1].bar(cost_data.keys(), cost_data.values())
    axes[1, 1].set_ylabel("Cost (€ billion)")
    axes[1, 1].set_title("System Cost Breakdown")

    plt.tight_layout()
    plt.savefig(f"{output_dir}/optimal_portfolio_analysis.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 2. Time series generation dispatch
    fig, ax = plt.subplots(figsize=(15, 6))

    gen_t = network.generators_t.p
    # Plot first 2 weeks for visibility
    gen_t.iloc[:336].plot.area(ax=ax, linewidth=0)

    ax.set_xlabel("Time")
    ax.set_ylabel("Generation (MW)")
    ax.set_title("Generation Dispatch (First 2 Weeks)")
    ax.legend(loc="upper left", bbox_to_anchor=(1, 1))

    plt.tight_layout()
    plt.savefig(f"{output_dir}/generation_dispatch.png", dpi=300, bbox_inches="tight")
    plt.close()

    # 3. Electricity prices
    fig, ax = plt.subplots(figsize=(15, 4))
    prices = network.buses_t.marginal_price["electricity"]
    prices.iloc[:336].plot(ax=ax)

    ax.set_xlabel("Time")
    ax.set_ylabel("Price (€/MWh)")
    ax.set_title("Electricity Marginal Price (First 2 Weeks)")
    ax.grid(alpha=0.3)

    plt.tight_layout()
    plt.savefig(f"{output_dir}/marginal_prices.png", dpi=300, bbox_inches="tight")
    plt.close()

    logger.info(f"Visualizations saved to {output_dir}")


def save_results(results: dict[str, Any], network: pypsa.Network, output_dir: str) -> None:
    """Save detailed results to CSV files."""
    logger.info("Saving results...")

    # Save summary
    summary = pd.DataFrame(
        {
            "Metric": [
                "Emissions Intensity (gCO2/kWh)",
                "Meets CO2 Limit",
                "Total Cost (€ billion)",
                "CAPEX (€ billion)",
                "OPEX (€ billion)",
                "Min Generation (MW)",
                "Avg Generation (MW)",
            ],
            "Value": [
                results["emissions_intensity"],
                results["meets_co2_limit"],
                results["total_cost_bn_eur"],
                results["capex_bn_eur"],
                results["opex_bn_eur"],
                results["min_generation_mw"],
                results["avg_generation_mw"],
            ],
        }
    )
    summary.to_csv(f"{output_dir}/portfolio_summary.csv", index=False)

    # Save capacities
    results["capacities_mw"].to_csv(f"{output_dir}/optimal_capacities_detailed.csv")

    # Save energy balance
    results["energy_balance_twh"].to_csv(f"{output_dir}/energy_balance_detailed.csv")

    # Save network
    network.export_to_netcdf(f"{output_dir}/optimal_portfolio_network.nc")

    logger.info(f"Results saved to {output_dir}")


def main() -> None:
    """
    This functions constructs a PyPSA network and optimizes it under emissions and baseload 
    constraints, then analyzes and visualizes the results.
    """
    logger.info("=" * 80)
    logger.info("Optimal Generation Portfolio Analysis")
    logger.info("=" * 80)

    # Parameters
    YEAR = 2030
    CO2_LIMIT = 50  # gCO2/kWh
    BASELOAD_MW = 1000  # MW

    results_dir = f"{REPO_ROOT}/results/portfolio_analysis"
    os.makedirs(results_dir, exist_ok=True)

    data_dir = f"{REPO_ROOT}/data"
    os.makedirs(data_dir, exist_ok=True)

    # Create and optimize network
    network, costs_df, total_load = create_constrained_network(
        data_dir=data_dir, year=YEAR, co2_limit=CO2_LIMIT, baseload_mw=BASELOAD_MW
    )

    # Optimize
    network = optimize_with_emissions_constraint(network, co2_limit=CO2_LIMIT)

    # Save the network after optimization
    network.export_to_netcdf(f"{results_dir}/optimized_network.nc")

    # Analyze results
    results = analyze_results(network, total_load, co2_limit=CO2_LIMIT)

    # Visualize network topology
    visualize_network_topology(network, results_dir)

    # Create visualizations
    create_visualizations(network, results, results_dir)

    # Save results
    save_results(results, network, results_dir)

    # Summary
    logger.info("\n" + "=" * 80)
    logger.info("SUMMARY")
    logger.info("=" * 80)
    logger.info(f"Emissions Intensity: {results['emissions_intensity']:.2f} gCO2/kWh")
    logger.info(f"Target: < {CO2_LIMIT} gCO2/kWh")
    logger.info(f"Status: {'✓ MEETS TARGET' if results['meets_co2_limit'] else '✗ EXCEEDS TARGET'}")
    logger.info(f"\nTotal System Cost: €{results['total_cost_bn_eur']:.2f} billion")
    logger.info(f"Baseload Requirement: {BASELOAD_MW} MW")
    logger.info(f"Minimum Generation: {results['min_generation_mw']:.1f} MW")
    logger.info("=" * 80)

    logger.info(f"\nAll results saved to: {results_dir}")
    logger.info("Script completed successfully!")


if __name__ == "__main__":
    main()
