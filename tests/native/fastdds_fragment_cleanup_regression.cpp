#include <fastdds/rtps/RTPSDomain.h>
#include <fastdds/rtps/attributes/RTPSParticipantAttributes.h>
#include <fastdds/rtps/attributes/ReaderAttributes.h>
#include <fastdds/rtps/reader/RTPSReader.h>
#include <fastdds/rtps/history/ReaderHistory.h>
#include <fastdds/rtps/builtin/data/WriterProxyData.h>
#include <fastdds/rtps/transport/UDPv4TransportDescriptor.h>

#include <algorithm>
#include <cstring>
#include <iostream>
#include <memory>

using namespace eprosima::fastrtps::rtps;

namespace
{
constexpr uint32_t kSampleSize = 921656;
constexpr uint32_t kFragmentSize = 65384;
constexpr int kPartialCycles = 100;

bool available_cache(RTPSReader* reader)
{
    CacheChange_t* change = nullptr;
    const bool reserved = reader->reserveCache(&change, kSampleSize);
    if (reserved)
    {
        reader->releaseCache(change);
    }
    return reserved;
}

GUID_t make_writer_guid(const GUID_t& reader_guid, uint8_t prefix_xor)
{
    GUID_t writer_guid = reader_guid;
    writer_guid.guidPrefix.value[2] ^= prefix_xor;
    writer_guid.entityId.value[3] = 3;
    return writer_guid;
}

WriterProxyData make_writer_proxy(const GUID_t& writer_guid)
{
    WriterProxyData writer(1, 1);
    writer.guid(writer_guid);
    writer.m_qos.m_reliability.kind = eprosima::fastdds::dds::BEST_EFFORT_RELIABILITY_QOS;
    return writer;
}

bool send_fragment(
        RTPSReader* reader,
        const GUID_t& writer_guid,
        uint32_t sequence,
        uint32_t fragment_number)
{
    const uint32_t offset = (fragment_number - 1) * kFragmentSize;
    const uint32_t payload_size = std::min(kFragmentSize, kSampleSize - offset);
    CacheChange_t fragment(payload_size);
    fragment.writerGUID = writer_guid;
    fragment.sequenceNumber = SequenceNumber_t(0, sequence);
    fragment.serializedPayload.length = payload_size;
    std::memset(fragment.serializedPayload.data, 0, payload_size);
    fragment.setFragmentSize(kFragmentSize);
    return reader->processDataFragMsg(&fragment, kSampleSize, fragment_number, 1);
}

bool run()
{
    RTPSParticipantAttributes participant_attributes;
    participant_attributes.useBuiltinTransports = false;
    auto udp = std::make_shared<eprosima::fastdds::rtps::UDPv4TransportDescriptor>();
    udp->interfaceWhiteList.push_back("127.0.0.1");
    participant_attributes.userTransports.push_back(udp);

    constexpr uint32_t kIsolatedDomain = 217;
    RTPSParticipant* participant = RTPSDomain::createParticipant(
        kIsolatedDomain, participant_attributes);
    if (participant == nullptr)
    {
        std::cerr << "FAIL: could not create isolated Fast DDS participant\n";
        return false;
    }

    ReaderHistory history(HistoryAttributes(
        PREALLOCATED_WITH_REALLOC_MEMORY_MODE, kSampleSize, 1, 1));
    ReaderAttributes reader_attributes;
    RTPSReader* reader = RTPSDomain::createRTPSReader(
        participant, reader_attributes, &history);
    if (reader == nullptr)
    {
        RTPSDomain::removeRTPSParticipant(participant);
        std::cerr << "FAIL: could not create Fast DDS reader\n";
        return false;
    }

    const GUID_t writer_guid = make_writer_guid(reader->getGuid(), 0x55);
    const GUID_t survivor_guid = make_writer_guid(reader->getGuid(), 0x33);
    WriterProxyData writer = make_writer_proxy(writer_guid);
    WriterProxyData survivor = make_writer_proxy(survivor_guid);

    if (!available_cache(reader))
    {
        std::cerr << "FAIL: reader did not have a cache slot at startup\n";
        RTPSDomain::removeRTPSParticipant(participant);
        return false;
    }

    for (int cycle = 1; cycle <= kPartialCycles; ++cycle)
    {
        if (!reader->matched_writer_add(writer))
        {
            std::cerr << "FAIL: writer did not match at partial cycle " << cycle << '\n';
            RTPSDomain::removeRTPSParticipant(participant);
            return false;
        }
        if (!send_fragment(reader, writer_guid, static_cast<uint32_t>(cycle), 1))
        {
            std::cerr << "FAIL: first fragment was rejected at cycle " << cycle << '\n';
            RTPSDomain::removeRTPSParticipant(participant);
            return false;
        }

        const bool removed_by_lease = (cycle % 2) == 0;
        if (!reader->matched_writer_remove(writer_guid, removed_by_lease))
        {
            std::cerr << "FAIL: writer removal failed at cycle " << cycle << '\n';
            RTPSDomain::removeRTPSParticipant(participant);
            return false;
        }
        if (!available_cache(reader))
        {
            std::cerr << "FAIL: cache pool exhausted after partial writer removal at cycle "
                      << cycle << " (removed_by_lease=" << removed_by_lease << ")\n";
            RTPSDomain::removeRTPSParticipant(participant);
            return false;
        }
    }
    if (reader->matched_writer_remove(writer_guid, false))
    {
        std::cerr << "FAIL: repeated removal unexpectedly found a writer\n";
        RTPSDomain::removeRTPSParticipant(participant);
        return false;
    }
    for (int cycle = 0; cycle < 10; ++cycle)
    {
        if (!reader->matched_writer_add(writer) ||
                !reader->matched_writer_remove(writer_guid, (cycle % 2) == 0) ||
                !available_cache(reader))
        {
            std::cerr << "FAIL: no-fragment writer removal failed at cycle " << cycle << '\n';
            RTPSDomain::removeRTPSParticipant(participant);
            return false;
        }
    }
    std::cout << "PASS: " << kPartialCycles
              << " incomplete fragmented samples reclaimed across lease and explicit removals\n";
    std::cout << "PASS: repeated removal and no-fragment writer removals preserve cache availability\n";

    // Keep a second writer matched while removing the partial writer, then
    // deliver a complete fragmented sample from the surviving writer.
    constexpr uint32_t kCompleteSequence = 1;
    if (!reader->matched_writer_add(writer) || !reader->matched_writer_add(survivor) ||
            !send_fragment(reader, writer_guid, kPartialCycles + 11, 1) ||
            !reader->matched_writer_remove(writer_guid, false))
    {
        std::cerr << "FAIL: could not remove a partial writer while another writer survived\n";
        RTPSDomain::removeRTPSParticipant(participant);
        return false;
    }
    constexpr uint32_t fragment_count = (kSampleSize + kFragmentSize - 1) / kFragmentSize;
    for (uint32_t fragment = 1; fragment <= fragment_count; ++fragment)
    {
        if (!send_fragment(reader, survivor_guid, kCompleteSequence, fragment))
        {
            std::cerr << "FAIL: surviving writer fragment " << fragment << " was rejected\n";
            RTPSDomain::removeRTPSParticipant(participant);
            return false;
        }
    }
    if (history.getHistorySize() != 1)
    {
        std::cerr << "FAIL: surviving writer sample was not added to ReaderHistory\n";
        RTPSDomain::removeRTPSParticipant(participant);
        return false;
    }
    if (!reader->matched_writer_remove(survivor_guid, true) || history.getHistorySize() != 0)
    {
        std::cerr << "FAIL: unmatched surviving writer did not clear the completed history sample\n";
        RTPSDomain::removeRTPSParticipant(participant);
        return false;
    }
    if (!available_cache(reader))
    {
        std::cerr << "FAIL: completed sample cache was not returned after writer removal\n";
        RTPSDomain::removeRTPSParticipant(participant);
        return false;
    }
    std::cout << "PASS: surviving writer delivered a complete sample after peer writer removal\n";

    RTPSDomain::removeRTPSParticipant(participant);
    return true;
}
}  // namespace

int main()
{
    return run() ? 0 : 1;
}
