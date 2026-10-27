// Aggregate-only Ghidra headless function census.
// Do not print or persist function names, addresses, disassembly, or bytes.
import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.address.AddressSetView;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.listing.Instruction;
import ghidra.program.model.listing.InstructionIterator;
import ghidra.program.model.listing.Listing;
import ghidra.program.model.listing.FunctionManager;

import java.io.BufferedWriter;
import java.io.File;
import java.io.FileWriter;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

public class FunctionCensusSummary extends GhidraScript {

    private static boolean inRange(Address address, Address start, Address end) {
        return address.compareTo(start) >= 0 && address.compareTo(end) <= 0;
    }

    private static boolean isReturnLike(Instruction instruction) {
        String mnemonic = instruction.getMnemonicString().toLowerCase(Locale.ROOT);
        String rendered = instruction.toString().toLowerCase(Locale.ROOT).replace(" ", "");
        if ("bx".equals(mnemonic) && rendered.endsWith("bx lr".replace(" ", ""))) {
            return true;
        }
        if ("mov".equals(mnemonic) && rendered.endsWith("movpc,lr")) {
            return true;
        }
        if ("pop".equals(mnemonic) && rendered.contains("pc")) {
            return true;
        }
        return mnemonic.startsWith("ldm") &&
            rendered.contains("sp") && rendered.contains("pc");
    }

    private static String jsonEscape(String value) {
        return value.replace("\\", "\\\\").replace("\"", "\\\"");
    }

    private static List<Map.Entry<String, Long>> sortedEntries(Map<String, Long> counts) {
        List<Map.Entry<String, Long>> entries = new ArrayList<Map.Entry<String, Long>>(counts.entrySet());
        Collections.sort(entries, new Comparator<Map.Entry<String, Long>>() {
            @Override
            public int compare(Map.Entry<String, Long> left, Map.Entry<String, Long> right) {
                int byCount = Long.compare(right.getValue().longValue(), left.getValue().longValue());
                if (byCount != 0) {
                    return byCount;
                }
                return left.getKey().compareTo(right.getKey());
            }
        });
        return entries;
    }

    @Override
    protected void run() throws Exception {
        String[] args = getScriptArgs();
        if (args.length != 4) {
            throw new IllegalArgumentException(
                "expected summary path, private candidate path, text start address (hex), and logical text size (decimal)");
        }
        long textStartOffset = Long.parseLong(args[2].replace("0x", "").replace("0X", ""), 16);
        long textSize = Long.parseLong(args[3]);
        if (textStartOffset < 0 || textStartOffset > 0xffffffffL ||
            textSize <= 0 || textSize > 0x100000000L ||
            textStartOffset > 0xffffffffL - (textSize - 1)) {
            throw new IllegalArgumentException("text range is outside the 32-bit address space");
        }

        Address textStart = currentProgram.getAddressFactory().getDefaultAddressSpace().getAddress(textStartOffset);
        Address textEnd = textStart.add(textSize - 1);
        FunctionManager manager = currentProgram.getFunctionManager();
        Listing listing = currentProgram.getListing();

        long functionCount = 0;
        long functionsLe32 = 0;
        long functionsLe64 = 0;
        long functionsLe128 = 0;
        long leafCount = 0;
        long leafLe32 = 0;
        long leafLe64 = 0;
        long leafLe128 = 0;
        long returnLikeCount = 0;
        long leafLe64WithReturn = 0;
        long smallLeafInstructionCount = 0;
        long excludedOutOfTextBodies = 0;
        Map<String, Long> smallLeafMnemonics = new HashMap<String, Long>();
        // This sidecar is written only under the caller's private temporary directory.
        // It holds a bounded set of small, contiguous ARM functions ending in BX LR.
        // Python screens these candidates against the current narrow ARM-to-C subset.
        List<String> privateTranslationCandidates = new ArrayList<String>();
        long privateTranslationCandidatesOmitted = 0;
        final int maxPrivateTranslationCandidates = 10000;

        FunctionIterator functions = manager.getFunctions(true);
        while (functions.hasNext() && !monitor.isCancelled()) {
            Function function = functions.next();
            Address entry = function.getEntryPoint();
            if (!inRange(entry, textStart, textEnd)) {
                continue;
            }
            AddressSetView body = function.getBody();
            if (body == null || body.getNumAddresses() == 0L) {
                continue;
            }
            if (!inRange(body.getMinAddress(), textStart, textEnd) ||
                !inRange(body.getMaxAddress(), textStart, textEnd)) {
                excludedOutOfTextBodies++;
                continue;
            }

            long bodySize = body.getNumAddresses();
            boolean hasCall = false;
            boolean hasReturn = false;
            long instructionCount = 0;
            List<String> mnemonics = new ArrayList<String>();
            List<String> candidateWords = new ArrayList<String>();
            boolean candidateIsLinearA32 = true;
            boolean lastInstructionIsBxLr = false;
            long expectedInstructionAddress = body.getMinAddress().getOffset();

            InstructionIterator instructions = listing.getInstructions(body, true);
            while (instructions.hasNext()) {
                Instruction instruction = instructions.next();
                if (!inRange(instruction.getAddress(), textStart, textEnd)) {
                    continue;
                }
                instructionCount++;
                String mnemonic = instruction.getMnemonicString().toLowerCase(Locale.ROOT);
                mnemonics.add(mnemonic);

                long instructionAddress = instruction.getAddress().getOffset();
                if (instructionAddress != expectedInstructionAddress || instruction.getLength() != 4) {
                    candidateIsLinearA32 = false;
                }
                expectedInstructionAddress = instructionAddress + instruction.getLength();
                lastInstructionIsBxLr = "bx".equals(mnemonic) &&
                    "bxlr".equals(instruction.toString().toLowerCase(Locale.ROOT).replace(" ", ""));
                byte[] encoding = instruction.getBytes();
                if (encoding == null || encoding.length != 4) {
                    candidateIsLinearA32 = false;
                } else {
                    long word = (encoding[0] & 0xffL) |
                        ((encoding[1] & 0xffL) << 8) |
                        ((encoding[2] & 0xffL) << 16) |
                        ((encoding[3] & 0xffL) << 24);
                    candidateWords.add(String.format(Locale.ROOT, "\"0x%08X\"", word));
                }
                if (instruction.getFlowType().isCall()) {
                    hasCall = true;
                }
                if (isReturnLike(instruction)) {
                    hasReturn = true;
                }
            }
            if (instructionCount == 0) {
                continue;
            }

            functionCount++;
            if (bodySize <= 32) {
                functionsLe32++;
            }
            if (bodySize <= 64) {
                functionsLe64++;
            }
            if (bodySize <= 128) {
                functionsLe128++;
            }

            boolean leaf = !hasCall;
            if (leaf) {
                leafCount++;
                if (bodySize <= 32) {
                    leafLe32++;
                }
                if (bodySize <= 64) {
                    leafLe64++;
                    smallLeafInstructionCount += instructionCount;
                    if (hasReturn) {
                        leafLe64WithReturn++;
                    }
                    for (String mnemonic : mnemonics) {
                        Long old = smallLeafMnemonics.get(mnemonic);
                        smallLeafMnemonics.put(mnemonic, Long.valueOf(old == null ? 1 : old.longValue() + 1));
                    }
                }
                if (bodySize <= 128) {
                    leafLe128++;
                }
            }
            if (hasReturn) {
                returnLikeCount++;
            }

            boolean translationCandidate =
                !hasCall &&
                lastInstructionIsBxLr &&
                body.getNumAddressRanges() == 1 &&
                bodySize >= 8 && bodySize <= 64 &&
                bodySize == instructionCount * 4 &&
                candidateIsLinearA32 &&
                candidateWords.size() == instructionCount;
            if (translationCandidate) {
                if (privateTranslationCandidates.size() < maxPrivateTranslationCandidates) {
                    StringBuilder wordsJson = new StringBuilder("[");
                    for (int wordIndex = 0; wordIndex < candidateWords.size(); wordIndex++) {
                        if (wordIndex > 0) {
                            wordsJson.append(",");
                        }
                        wordsJson.append(candidateWords.get(wordIndex));
                    }
                    wordsJson.append("]");
                    privateTranslationCandidates.add(
                        "{\"entry_address\":\"0x" +
                        String.format(Locale.ROOT, "%08X", entry.getOffset()) +
                        "\",\"body_size_bytes\":" + bodySize +
                        ",\"instruction_count\":" + instructionCount +
                        ",\"words\":" + wordsJson.toString() + "}");
                } else {
                    privateTranslationCandidatesOmitted++;
                }
            }
        }

        StringBuilder topMnemonics = new StringBuilder("[");
        List<Map.Entry<String, Long>> ordered = sortedEntries(smallLeafMnemonics);
        int emitted = 0;
        for (Map.Entry<String, Long> item : ordered) {
            if (emitted >= 20) {
                break;
            }
            if (emitted > 0) {
                topMnemonics.append(",");
            }
            topMnemonics.append("{\"mnemonic\":\"")
                .append(jsonEscape(item.getKey()))
                .append("\",\"count\":")
                .append(item.getValue().longValue())
                .append("}");
            emitted++;
        }
        topMnemonics.append("]");

        String json = "{\n" +
            "  \"schema_version\": 1,\n" +
            "  \"status\": \"pass\",\n" +
            "  \"text_size_bytes\": " + textSize + ",\n" +
            "  \"functions_with_entry_inside_text\": " + functionCount + ",\n" +
            "  \"functions_le_32_bytes\": " + functionsLe32 + ",\n" +
            "  \"functions_le_64_bytes\": " + functionsLe64 + ",\n" +
            "  \"functions_le_128_bytes\": " + functionsLe128 + ",\n" +
            "  \"leaf_functions\": " + leafCount + ",\n" +
            "  \"leaf_functions_le_32_bytes\": " + leafLe32 + ",\n" +
            "  \"leaf_functions_le_64_bytes\": " + leafLe64 + ",\n" +
            "  \"leaf_functions_le_128_bytes\": " + leafLe128 + ",\n" +
            "  \"functions_with_return_like_instruction\": " + returnLikeCount + ",\n" +
            "  \"leaf_functions_le_64_bytes_with_return_like_instruction\": " + leafLe64WithReturn + ",\n" +
            "  \"instructions_in_leaf_functions_le_64_bytes\": " + smallLeafInstructionCount + ",\n" +
            "  \"excluded_bodies_crossing_text_bounds\": " + excludedOutOfTextBodies + ",\n" +
            "  \"top_mnemonics_in_leaf_functions_le_64_bytes\": " + topMnemonics.toString() + ",\n" +
            "  \"function_boundaries_verified\": false,\n" +
            "  \"addresses_emitted\": false,\n" +
            "  \"disassembly_emitted\": false,\n" +
            "  \"interpretation\": \"Ghidra auto-analysis inventory only; function starts/bodies can be heuristic and are not validated game functions.\"\n" +
            "}\n";

        File destination = new File(args[0]);
        File parent = destination.getParentFile();
        if (parent != null && !parent.exists() && !parent.mkdirs()) {
            throw new java.io.IOException("could not create temporary summary directory");
        }
        BufferedWriter writer = new BufferedWriter(new FileWriter(destination));
        try {
            writer.write(json);
        } finally {
            writer.close();
        }

        File candidateDestination = new File(args[1]);
        File candidateParent = candidateDestination.getParentFile();
        if (candidateParent != null && !candidateParent.exists() && !candidateParent.mkdirs()) {
            throw new java.io.IOException("could not create private candidate sidecar directory");
        }
        StringBuilder candidatesJson = new StringBuilder("{\n")
            .append("  \"schema_version\": 1,\n")
            .append("  \"omitted_candidate_count\": ").append(privateTranslationCandidatesOmitted).append(",\n")
            .append("  \"candidates\": [");
        for (int candidateIndex = 0; candidateIndex < privateTranslationCandidates.size(); candidateIndex++) {
            if (candidateIndex > 0) {
                candidatesJson.append(",");
            }
            candidatesJson.append("\n    ").append(privateTranslationCandidates.get(candidateIndex));
        }
        if (!privateTranslationCandidates.isEmpty()) {
            candidatesJson.append("\n  ");
        }
        candidatesJson.append("]\n}\n");
        BufferedWriter candidateWriter = new BufferedWriter(new FileWriter(candidateDestination));
        try {
            candidateWriter.write(candidatesJson.toString());
        } finally {
            candidateWriter.close();
        }
    }
}
