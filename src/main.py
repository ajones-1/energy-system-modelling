import pandas as pd
import matplotlib.pyplot as plt
from loguru import logger
import json
import pypsa
from pypsa.common import annuity

from utils.general_functions import get_repo_root, load_data

REPO_ROOT = get_repo_root()

def main():

    logger.info("Starting energy system optimization model...")

    # Load data
    year = 2030
    url = f"https://raw.githubusercontent.com/PyPSA/technology-data/master/outputs/costs_{year}.csv"
    costs_df = load_data(url, f"{REPO_ROOT}/data/costs_{year}.csv", use_cache=True)

    costs_df.loc[costs_df.unit.str.contains("/kW"), "value"] *= 1e3
    costs_df = costs_df.value.unstack().fillna({"discount rate": 0.07, "lifetime": 20, "FOM": 0})

    costs_df["marginal_cost"] = costs_df["VOM"] + costs_df["fuel"] / costs_df["efficiency"]

    a = costs_df.apply(lambda x: annuity(x["discount rate"], x["lifetime"]), axis=1)
    costs_df["capital_cost"] = (a + costs_df["FOM"] / 100) * costs_df["investment"]

    # Load time series data
    resolution = 3  # hours
    url = "https://tubcloud.tu-berlin.de/s/9toBssWEdaLgHzq/download/time-series.csv"
    time_series_df = load_data(
        url, f"{REPO_ROOT}/data/time-series_{year}.csv", use_cache=True
    )[::resolution]

    # Initialise model
    n = pypsa.Network()
    n.add("Bus", "electricity", carrier="electricity")
    n.set_snapshots(time_series_df.index)
    logger.info(f"Network initialized with {len(n.snapshots)} snapshots.")

    n.snapshot_weightings.loc[:, :] = resolution

    # Add carriers for plotting, load from config file
    with open(f"{REPO_ROOT}/config/carriers.json") as f:
        carriers_config = json.load(f)
    carriers = list(carriers_config["carriers"].keys())
    colors = list(carriers_config["carriers"].values())

    n.add("Carrier", carriers, color=colors)
    logger.info("Added carriers to the network.")

    # Add load to the network
    n.add(
        "Load",
        "demand",
        bus="electricity",
        p_set=time_series_df.load_mw,
    )
    logger.info("Added load to the network.")

    # Add a load shedding generator with high marginal cost
    n.add(
        "Generator",
        "load shedding",
        bus="electricity",
        carrier="load shedding",
        marginal_cost=2000,
        p_nom=time_series_df.load_mw.max(),
    )
    logger.info("Added load shedding generator to the network.")

    # Add renewable generators
    n.add(
        "Generator",
        "wind",
        bus="electricity",
        carrier="wind",
        p_max_pu=time_series_df.wind_pu,
        capital_cost=costs_df.at["onwind", "capital_cost"],
        marginal_cost=costs_df.at["onwind", "marginal_cost"],
        p_nom_extendable=True,
    )
    logger.info("Added wind generator to the network.")

    n.add(
        "Generator",
        "solar",
        bus="electricity",
        carrier="solar",
        p_max_pu=time_series_df.pv_pu,
        capital_cost=costs_df.at["solar", "capital_cost"],
        marginal_cost=costs_df.at["solar", "marginal_cost"],
        p_nom_extendable=True,
    )
    logger.info("Added solar generator to the network.")

    # Add hydrogen storage and related components
    n.add("Bus", "hydrogen", carrier="hydrogen")
    logger.info("Added hydrogen bus to the network.")

    n.add(
        "Link",
        "electrolysis",
        bus0="electricity",
        bus1="hydrogen",
        carrier="electrolysis",
        p_nom_extendable=True,
        efficiency=costs_df.at["electrolysis", "efficiency"],
        capital_cost=costs_df.at["electrolysis", "capital_cost"],
    )
    logger.info("Added electrolysis link to the network.")

    n.add(
        "Link",
        "turbine",
        bus0="hydrogen",
        bus1="electricity",
        carrier="turbine",
        p_nom_extendable=True,
        efficiency=costs_df.at["OCGT", "efficiency"],
        capital_cost=costs_df.at["OCGT", "capital_cost"] / costs_df.at["OCGT", "efficiency"],
    )
    logger.info("Added turbine link to the network.")

    logger.info("Starting optimization...")
    n.optimize(solver_name="highs")
    logger.info("Optimization completed.")

    tsc = (
        pd.concat([n.statistics.capex(), n.statistics.opex()], axis=1).sum(axis=1).div(1e9)
    )
    logger.info(tsc)

    logger.info(f"{tsc.sum():.2f} billion € total annual system costs")

    logger.info(n.statistics.optimal_capacity().div(1e3))

    logger.info(n.statistics.energy_balance(bus_carrier="electricity").sort_values().div(1e6))

    # Create and save energy balance plot
    n.statistics.energy_balance.plot.area(linewidth=0, bus_carrier="electricity")
    plt.title("Energy Balance by Carrier")
    plt.ylabel("Energy (TWh)")
    plt.tight_layout()
    plt.savefig(f"{REPO_ROOT}/results/energy_balance_electricity.png", dpi=300, bbox_inches='tight')
    plt.close()  # Close the figure to free memory

    # Create and save marginal price plot
    n.buses_t.marginal_price.plot(figsize=(7, 2))
    plt.title("Electricity Marginal Price")
    plt.ylabel("Price (€/MWh)")
    plt.xlabel("Time")
    plt.tight_layout()
    plt.savefig(f"{REPO_ROOT}/results/marginal_price.png", dpi=300, bbox_inches='tight')
    plt.close()  # Close the figure to free memory

    # Save the optimized network to a file
    n.export_to_netcdf(f"{REPO_ROOT}/results/optimized_network.nc")
    logger.info("Saved optimized network to file.")

    logger.info("Script completed successfully.")

if __name__ == "__main__":
    main()
