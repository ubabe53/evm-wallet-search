export type Erc20TransferEventLike = {
  chainId: number;
  block: {
    number: bigint | number;
    timestamp: number;
  };
  transaction: {
    hash: string;
    transactionIndex?: number | null;
    from?: string | null;
    to?: string | null;
  };
  logIndex: number;
  srcAddress: string;
  params: {
    from: string;
    to: string;
    value: bigint;
  };
};

export type Erc20TransferEntity = {
  id: string;
  chainId: number;
  blockNumber: bigint;
  blockTimestamp: number;
  transactionHash: string;
  transactionIndex: number;
  transactionFromAddress: string | undefined;
  transactionToAddress: string | undefined;
  logIndex: number;
  tokenAddress: string;
  fromAddress: string;
  toAddress: string;
  valueRaw: bigint;
};

const lower = (value: string) => value.toLowerCase();
const lowerOptional = (value: string | null | undefined) => value ? lower(value) : undefined;

export function toErc20TransferEntity(event: Erc20TransferEventLike): Erc20TransferEntity {
  const blockNumber = BigInt(event.block.number);

  return {
    id: `${event.chainId}-${event.transaction.hash.toLowerCase()}-${event.logIndex}`,
    chainId: event.chainId,
    blockNumber,
    blockTimestamp: event.block.timestamp,
    transactionHash: lower(event.transaction.hash),
    transactionIndex: event.transaction.transactionIndex ?? 0,
    transactionFromAddress: lowerOptional(event.transaction.from),
    transactionToAddress: lowerOptional(event.transaction.to),
    logIndex: event.logIndex,
    tokenAddress: lower(event.srcAddress),
    fromAddress: lower(event.params.from),
    toAddress: lower(event.params.to),
    valueRaw: event.params.value,
  };
}
