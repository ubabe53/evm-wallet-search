import { indexer } from "envio";
import { CONFIGURED_WALLET_ADDRESSES } from "../wallets";
import { toErc20TransferEntity } from "../transferEntity";

indexer.onEvent(
  {
    contract: "ERC20",
    event: "Transfer",
    wildcard: true,
    where: () => ({
      params: [{ from: CONFIGURED_WALLET_ADDRESSES }, { to: CONFIGURED_WALLET_ADDRESSES }],
    }),
  },
  async ({ event, context }) => {
    context.Erc20Transfer.set(toErc20TransferEntity(event));
  },
);
