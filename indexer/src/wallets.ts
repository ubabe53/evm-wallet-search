export const CONFIGURED_WALLETS = [
  {
    ens: "vitalik.eth",
    address: "0xd8da6bf26964af9d7eed9e03e53415d37aa96045",
    label: "Vitalik Buterin",
  },
] as const;

export const CONFIGURED_WALLET_ADDRESSES = CONFIGURED_WALLETS.map((wallet) => wallet.address);
