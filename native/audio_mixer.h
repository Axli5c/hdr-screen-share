#pragma once
#include <algorithm>
#include <cstdint>
#include <deque>
#include <map>
#include <vector>

class AudioMixer {
    size_t channels_, capacity_;
    uint64_t overflows_ = 0;
    std::map<uint32_t, std::deque<float>> sources_;
public:
    AudioMixer(size_t channels, size_t capacityFrames)
        : channels_(channels), capacity_(channels * capacityFrames) {}
    void push(uint32_t pid, const float* samples, size_t frames) {
        auto& queue = sources_[pid];
        const size_t count = frames * channels_;
        if (queue.size() + count > capacity_) {
            ++overflows_;
            const size_t excess = queue.size() + count - capacity_;
            const size_t drop = std::min(excess, queue.size());
            queue.erase(queue.begin(), queue.begin() + drop);
        }
        const size_t skip = count > capacity_ ? count - capacity_ : 0;
        for (size_t index = skip; index < count; ++index)
            queue.push_back(samples ? samples[index] : 0.0f);
    }
    void mix(float* output, size_t frames) {
        std::fill(output, output + frames * channels_, 0.0f);
        for (auto& source : sources_) {
            auto& queue = source.second;
            const size_t count = std::min(queue.size(), frames * channels_);
            for (size_t index = 0; index < count; ++index) {
                output[index] += queue.front();
                queue.pop_front();
            }
        }
        for (size_t index = 0; index < frames * channels_; ++index)
            output[index] = std::clamp(output[index], -1.0f, 1.0f);
    }
    size_t queued_frames() const {
        size_t maximum = 0;
        for (const auto& source : sources_) maximum = std::max(maximum, source.second.size() / channels_);
        return maximum;
    }
    uint64_t overflows() const { return overflows_; }
    void remove(uint32_t pid) { sources_.erase(pid); }
    void clear() { sources_.clear(); }
};
