const DEFAULT_WALLET_ADDRESS = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045";
const ADDRESS_PATTERN = /^0x[0-9a-f]{40}$/;
type EthereumAddress = `0x${string}`;

export function configuredWalletAddresses(
  environment: Record<string, string | undefined> = process.env,
): readonly EthereumAddress[] {
  const configured = environment.ENVIO_WALLET_SCAN_ADDRESS?.trim().toLowerCase();
  if (!configured) {
    return [DEFAULT_WALLET_ADDRESS];
  }
  if (!ADDRESS_PATTERN.test(configured)) {
    throw new Error("ENVIO_WALLET_SCAN_ADDRESS must be a canonical Ethereum address");
  }
  return [configured as EthereumAddress];
}

export const CONFIGURED_WALLET_ADDRESSES = configuredWalletAddresses();
